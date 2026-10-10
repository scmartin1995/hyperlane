"""Business-analyst chat: one turn of a thread (history -> provider with tools -> persisted messages)."""

from __future__ import annotations

import logging
from typing import Any

from ..db import session_scope, utcnow
from ..models import ChatMessage, ChatThread, Project, User
from ..services.events import bus
from .prompts import ba_system_prompt
from .provider import AgentResult, OnEvent, ProviderError, get_provider
from .tools import available_tools

log = logging.getLogger(__name__)

HISTORY_LIMIT = 40  # content-block turns replayed to the model


def _history(thread: ChatThread) -> list[dict[str, Any]]:
    """Rebuild the content-block conversation from stored messages."""
    turns: list[dict[str, Any]] = []
    for msg in thread.messages:
        raw = msg.raw or {}
        stored = raw.get("messages")
        if stored:
            turns.extend(stored)
        elif msg.role in ("user", "assistant") and msg.content:
            turns.append({"role": msg.role, "content": [{"type": "text", "text": msg.content}]})
    # keep the tail, but never start mid tool-exchange (a tool_result needs its tool_use)
    if len(turns) > HISTORY_LIMIT:
        turns = turns[-HISTORY_LIMIT:]
        while turns and (
            turns[0]["role"] != "user"
            or any(isinstance(b, dict) and b.get("type") == "tool_result" for b in turns[0].get("content") or [])
        ):
            turns.pop(0)
    return turns


def _title_from(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else "New conversation"
    first = first.lstrip("#*- ").strip()
    return (first[:57] + "…") if len(first) > 60 else first or "New conversation"


def serialize_message(msg: ChatMessage) -> dict[str, Any]:
    return {
        "id": msg.id,
        "thread_id": msg.thread_id,
        "role": msg.role,
        "content": msg.content,
        "tool_calls": msg.tool_calls or [],
        "usage": msg.usage or {},
        "created_at": msg.created_at.isoformat(),
    }


async def chat(thread: ChatThread, user_message: str, user: User, on_event: OnEvent = None) -> ChatMessage:
    """Run one turn. Emits ChatStreamEvents to `on_event`; persists user + assistant messages.

    `thread`/`user` may come from another session; only their ids are used.
    """
    thread_id, user_id = thread.id, user.id
    provider = get_provider()

    # 1. persist the user message + build the prompt inside a short session
    with session_scope() as db:
        th = db.get(ChatThread, thread_id)
        if th is None:
            raise ValueError("Thread not found")
        u = db.get(User, user_id)
        project = db.get(Project, th.project_id) if th.project_id else None
        system = ba_system_prompt(db, u, project, th)
        history = _history(th)
        user_turn = {"role": "user", "content": [{"type": "text", "text": user_message}]}
        history.append(user_turn)
        if not th.messages and th.title in ("", "New conversation"):
            th.title = _title_from(user_message)
        db.add(ChatMessage(thread_id=th.id, role="user", content=user_message, raw={"messages": [user_turn]}))
        session_id = th.provider_session
        msg_count = len(th.messages)

    tools = available_tools()
    # 2. run the provider (tools open their own sessions)
    try:
        result = await provider.run_tools(
            system, history, tools, on_event, user_id=user_id, session_id=session_id
        )
    except ProviderError as exc:
        log.warning("chat turn failed: %s", exc)
        result = AgentResult(text=f"_I couldn't reach Claude: {exc}_", stop_reason="error", error=str(exc))
        result.raw_messages = [{"role": "assistant", "content": [{"type": "text", "text": result.text}]}]
        await _safe_emit(on_event, {"type": "error", "error": str(exc)})
    except Exception as exc:
        log.exception("chat turn crashed")
        result = AgentResult(text="_Something went wrong on my side; try again._", stop_reason="error", error=str(exc))
        result.raw_messages = [{"role": "assistant", "content": [{"type": "text", "text": result.text}]}]
        await _safe_emit(on_event, {"type": "error", "error": f"{exc.__class__.__name__}: {exc}"})

    if not result.text.strip():
        result.text = "_(no reply)_"
        result.raw_messages.append({"role": "assistant", "content": [{"type": "text", "text": result.text}]})

    # 3. persist the assistant message (replayable content blocks in raw)
    raw_assistant = [m for m in result.raw_messages if not (m["role"] == "user" and _is_plain_user_turn(m))]
    with session_scope() as db:
        th = db.get(ChatThread, thread_id)
        assistant = ChatMessage(
            thread_id=thread_id,
            role="assistant",
            content=result.text,
            tool_calls=[
                {"name": c["name"], "input": c.get("input"), "result_summary": c.get("result_summary", "")}
                for c in result.tool_calls
            ],
            raw={"messages": raw_assistant, "stop_reason": result.stop_reason, "error": result.error},
            usage=result.usage or {},
        )
        db.add(assistant)
        if th is not None:
            if result.session_id and result.session_id != th.provider_session:
                th.provider_session = result.session_id
            th.updated_at = utcnow()
        db.flush()
        payload = serialize_message(assistant)
        project_id = th.project_id if th else None

    bus.emit(
        "chat.message",
        project_id=project_id,
        entity_type="chat_thread",
        entity_id=thread_id,
        actor_id=user_id,
        data={"message_id": payload["id"], "role": "assistant", "turn": msg_count // 2 + 1},
    )
    await _safe_emit(on_event, {"type": "message", "message": payload})
    return assistant


def _is_plain_user_turn(m: dict[str, Any]) -> bool:
    """The claude-code path echoes the user prompt in raw_messages; the user ChatMessage already stores it."""
    content = m.get("content") or []
    return all(isinstance(b, dict) and b.get("type") == "text" for b in content)


async def _safe_emit(on_event: OnEvent, ev: dict[str, Any]) -> None:
    from .provider import _emit

    try:
        await _emit(on_event, ev)
    except Exception:
        log.debug("on_event failed", exc_info=True)
