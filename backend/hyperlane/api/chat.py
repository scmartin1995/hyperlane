"""BA agent chat threads + streaming messages, and agent status."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from ..agent import ba
from ..agent.provider import get_provider
from ..models import ChatThread, Project
from ..schemas.common import AgentStatusOut, ChatMessageOut, ChatThreadOut
from ..services.auth import DB, CurrentUser

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


class ThreadIn(BaseModel):
    project_id: str | None = None
    mode: str | None = None
    context: dict[str, Any] | None = None
    title: str | None = None


class MessageIn(BaseModel):
    content: str


@router.get("/agent/status", response_model=AgentStatusOut)
def agent_status():
    return get_provider().status()


@router.get("/chat/threads", response_model=list[ChatThreadOut])
def list_threads(db: DB, user: CurrentUser):
    rows = db.scalars(
        select(ChatThread).where(ChatThread.user_id == user.id).order_by(ChatThread.updated_at.desc()).limit(100)
    ).all()
    return [_thread_brief(t) for t in rows]


@router.post("/chat/threads", response_model=ChatThreadOut, status_code=201)
def create_thread(body: ThreadIn, db: DB, user: CurrentUser):
    if body.project_id and db.get(Project, body.project_id) is None:
        raise HTTPException(404, "Project not found")
    thread = ChatThread(
        user_id=user.id,
        project_id=body.project_id,
        mode=body.mode or "analyst",
        context=body.context or {},
        title=body.title or "New conversation",
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return _thread_out(thread)


def _get_thread(db, thread_id: str, user) -> ChatThread:
    thread = db.get(ChatThread, thread_id)
    if thread is None or thread.user_id != user.id:
        raise HTTPException(404, "Thread not found")
    return thread


def _thread_brief(thread: ChatThread) -> ChatThreadOut:
    """Thread without its messages (avoids loading every message for the list view)."""
    return ChatThreadOut(
        id=thread.id,
        user_id=thread.user_id,
        project_id=thread.project_id,
        title=thread.title,
        mode=thread.mode,
        context=thread.context or {},
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=None,
    )


def _thread_out(thread: ChatThread) -> ChatThreadOut:
    out = _thread_brief(thread)
    out.messages = [ChatMessageOut.model_validate(m) for m in thread.messages]
    return out


@router.get("/chat/threads/{thread_id}", response_model=ChatThreadOut)
def get_thread(thread_id: str, db: DB, user: CurrentUser):
    return _thread_out(_get_thread(db, thread_id, user))


@router.delete("/chat/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: str, db: DB, user: CurrentUser):
    thread = _get_thread(db, thread_id, user)
    db.delete(thread)
    db.commit()


@router.post("/chat/threads/{thread_id}/messages")
async def send_message(thread_id: str, body: MessageIn, request: Request, db: DB, user: CurrentUser):
    """SSE stream of ChatStreamEvent JSON (`data:` per event). Ends with `{"type":"done"}`."""
    thread = _get_thread(db, thread_id, user)
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "Message is empty")
    db.expunge(thread)
    db.expunge(user)
    db.close()

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def on_event(ev: dict[str, Any]) -> None:
        await queue.put(ev)

    async def run() -> None:
        try:
            await ba.chat(thread, content, user, on_event)
        except Exception as exc:
            log.exception("chat turn failed")
            await queue.put({"type": "error", "error": f"{exc.__class__.__name__}: {exc}"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(run())

    async def gen():
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield {"event": "ping", "data": "{}"}
                    continue
                if ev is None:
                    break
                yield {"data": json.dumps(ev, default=str)}
            yield {"data": json.dumps({"type": "done"})}
        finally:
            if not task.done():
                # let the turn finish persisting even if the client went away
                await asyncio.shield(task)

    return EventSourceResponse(gen())
