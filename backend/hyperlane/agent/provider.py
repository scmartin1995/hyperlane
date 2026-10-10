"""LLM provider abstraction: Anthropic API, Amazon Bedrock, Claude Code subscription, or a stub.

Two operations:
  * `run_tools`  - an agentic loop with our tools, streaming `ChatStreamEvent`-shaped dicts to `on_event`
  * `complete`   - a single completion, optionally constrained to a JSON schema / pydantic model

Message history is kept as Anthropic content-block messages so multi-turn tool conversations replay
exactly on the API path. The claude-code path keeps state in its own session (`resume=`).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..config import ROOT, Settings, get_settings
from .tools import ToolSpec, execute

log = logging.getLogger(__name__)

OnEvent = Callable[[dict[str, Any]], Awaitable[None] | None] | None
MAX_TOKENS = 8000
MAX_TURNS = 12


class ProviderError(RuntimeError):
    """The provider is unavailable or refused the request. Message is safe to show to users."""


@dataclass
class AgentResult:
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # {id, name, input, result_summary, ok}
    raw_messages: list[dict[str, Any]] = field(default_factory=list)  # content-block turns for replay
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str = "end_turn"
    session_id: str | None = None
    error: str | None = None


async def _emit(on_event: OnEvent, event: dict[str, Any]) -> None:
    if on_event is None:
        return
    res = on_event(event)
    if inspect.isawaitable(res):
        await res


def parse_json_text(text: str) -> Any:
    """Parse JSON out of model text, tolerating code fences and chatter around the object."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0]
    if not starts:
        raise ProviderError("The model did not return JSON.")
    start = min(starts)
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if end <= start:
        raise ProviderError("The model returned malformed JSON.")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProviderError(f"The model returned malformed JSON: {exc}") from exc


def schema_of(json_schema: dict[str, Any] | type[BaseModel] | None) -> dict[str, Any] | None:
    if json_schema is None:
        return None
    if isinstance(json_schema, dict):
        return json_schema
    return json_schema.model_json_schema()


def validate_output(data: Any, json_schema: dict[str, Any] | type[BaseModel] | None) -> Any:
    if isinstance(json_schema, type) and issubclass(json_schema, BaseModel):
        return json_schema.model_validate(data).model_dump(mode="json")
    return data


def text_of_messages(messages: list[dict[str, Any]]) -> str:
    """Flatten content-block messages into a readable transcript (used when we can't replay blocks)."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content")
        if isinstance(content, str):
            lines.append(f"{role}: {content}")
            continue
        for block in content or []:
            t = block.get("type")
            if t == "text":
                lines.append(f"{role}: {block.get('text', '')}")
            elif t == "tool_use":
                lines.append(f"{role} called {block.get('name')}({json.dumps(block.get('input'))[:300]})")
            elif t == "tool_result":
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                lines.append(f"tool result: {str(body)[:300]}")
    return "\n".join(lines)


def last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return content
        for block in content or []:
            if block.get("type") == "text":
                return block.get("text", "")
    return ""


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class LLMProvider:
    name = "none"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.llm_model

    async def run_tools(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        on_event: OnEvent = None,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        max_turns: int = MAX_TURNS,
    ) -> AgentResult:
        raise NotImplementedError

    async def complete(
        self,
        system: str | None,
        prompt: str,
        *,
        json_schema: dict[str, Any] | type[BaseModel] | None = None,
        max_tokens: int = MAX_TOKENS,
    ) -> str | dict[str, Any]:
        raise NotImplementedError

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "available": False, "detail": "No provider configured"}

    @property
    def available(self) -> bool:
        return bool(self.status().get("available"))


# ---------------------------------------------------------------------------
# Anthropic API / Bedrock
# ---------------------------------------------------------------------------


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: Settings, *, bedrock: bool = False) -> None:
        super().__init__(settings)
        self.bedrock = bedrock
        if bedrock:
            self.name = "bedrock"
            self.model = settings.bedrock_model
        self._client: Any = None
        self._client_error: str | None = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self.bedrock:
            try:
                from anthropic import AsyncAnthropicBedrockMantle
            except ImportError as exc:  # the `bedrock` extra isn't installed
                self._client_error = "Bedrock support needs `uv sync --extra bedrock` (anthropic[bedrock])."
                raise ProviderError(self._client_error) from exc
            try:
                self._client = AsyncAnthropicBedrockMantle(aws_region=self.settings.aws_region)
            except Exception as exc:
                self._client_error = f"Bedrock client could not start: {exc}"
                raise ProviderError(self._client_error) from exc
        else:
            from anthropic import AsyncAnthropic

            kwargs: dict[str, Any] = {}
            if self.settings.anthropic_api_key:
                kwargs["api_key"] = self.settings.anthropic_api_key
            try:
                self._client = AsyncAnthropic(**kwargs)
            except Exception as exc:
                self._client_error = f"Anthropic client could not start: {exc}"
                raise ProviderError(self._client_error) from exc
        return self._client

    def status(self) -> dict[str, Any]:
        if self.bedrock:
            try:
                import anthropic.lib.bedrock  # noqa: F401
            except ImportError:
                return {
                    "provider": self.name,
                    "model": self.model,
                    "available": False,
                    "detail": "Install the bedrock extra: uv sync --extra bedrock",
                }
            ok = bool(self.settings.aws_region)
            detail = f"Amazon Bedrock in {self.settings.aws_region}" if ok else "Set AWS_REGION (and AWS credentials)"
            return {"provider": self.name, "model": self.model, "available": ok, "detail": detail}
        try:
            self._get_client()
        except ProviderError as exc:
            return {"provider": self.name, "model": self.model, "available": False, "detail": str(exc)}
        detail = "Anthropic API key from .env" if self.settings.anthropic_api_key else "Anthropic API (env/profile auth)"
        if self._client_error:
            detail = self._client_error
        return {"provider": self.name, "model": self.model, "available": True, "detail": detail}

    @staticmethod
    def _system_blocks(system: str | None) -> list[dict[str, Any]] | None:
        if not system:
            return None
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    @staticmethod
    def _dump_blocks(content: list[Any]) -> list[dict[str, Any]]:
        return [b.model_dump(mode="json", exclude_none=True) for b in content]

    async def run_tools(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        on_event: OnEvent = None,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        max_turns: int = MAX_TURNS,
    ) -> AgentResult:
        import anthropic

        client = self._get_client()
        history = [dict(m) for m in messages]
        result = AgentResult()
        tool_map = {t.name: t for t in tools}
        text_parts: list[str] = []
        usage = {"input_tokens": 0, "output_tokens": 0}

        for _turn in range(max_turns):
            try:
                async with client.messages.stream(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    system=self._system_blocks(system),
                    messages=history,
                    tools=[t.anthropic() for t in tools] or anthropic.NOT_GIVEN,
                ) as stream:
                    async for ev in stream:
                        if ev.type == "text":
                            await _emit(on_event, {"type": "text", "delta": ev.text})
                    final = await stream.get_final_message()
            except anthropic.APIStatusError as exc:
                raise ProviderError(f"Claude API error ({exc.status_code}): {exc.message}") from exc
            except anthropic.APIConnectionError as exc:
                raise ProviderError(f"Could not reach the Claude API: {exc}") from exc

            if final.usage:
                usage["input_tokens"] += final.usage.input_tokens or 0
                usage["output_tokens"] += final.usage.output_tokens or 0
            assistant_blocks = self._dump_blocks(final.content)
            history.append({"role": "assistant", "content": assistant_blocks})
            result.raw_messages.append({"role": "assistant", "content": assistant_blocks})
            for b in final.content:
                if b.type == "text" and b.text.strip():
                    text_parts.append(b.text)
            result.stop_reason = final.stop_reason or "end_turn"

            if final.stop_reason == "refusal":
                details = getattr(final, "stop_details", None)
                why = getattr(details, "explanation", None) or "safety policy"
                result.error = f"Claude declined this request ({why})."
                if not text_parts:
                    text_parts.append("I can't help with that one.")
                break
            if final.stop_reason == "max_tokens":
                text_parts.append("\n\n_(I ran out of room; ask me to continue.)_")
                break
            if final.stop_reason == "pause_turn":
                continue
            if final.stop_reason != "tool_use":
                break

            tool_uses = [b for b in final.content if b.type == "tool_use"]
            if not tool_uses:
                break
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                tool_input = dict(tu.input or {})
                await _emit(on_event, {"type": "tool_call", "id": tu.id, "name": tu.name, "input": tool_input})
                spec = tool_map.get(tu.name)
                if spec is None:
                    outcome_ok, text, summary = False, f"Unknown tool {tu.name}", f"unknown tool {tu.name}"
                else:
                    outcome = await asyncio.to_thread(execute, spec, user_id, tool_input)
                    outcome_ok, text, summary = outcome.ok, outcome.as_text(), outcome.summary
                await _emit(
                    on_event,
                    {"type": "tool_result", "id": tu.id, "name": tu.name, "summary": summary, "ok": outcome_ok},
                )
                result.tool_calls.append(
                    {"id": tu.id, "name": tu.name, "input": tool_input, "result_summary": summary, "ok": outcome_ok}
                )
                block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tu.id, "content": text}
                if not outcome_ok:
                    block["is_error"] = True
                tool_results.append(block)
            # all results for the batch go back in ONE user message
            history.append({"role": "user", "content": tool_results})
            result.raw_messages.append({"role": "user", "content": tool_results})
        else:
            text_parts.append("\n\n_(Stopping here; that was a lot of steps. Ask me to keep going.)_")
            result.stop_reason = "max_turns"

        result.text = "\n\n".join(p.strip() for p in text_parts if p.strip())
        result.usage = usage
        return result

    async def complete(
        self,
        system: str | None,
        prompt: str,
        *,
        json_schema: dict[str, Any] | type[BaseModel] | None = None,
        max_tokens: int = MAX_TOKENS,
    ) -> str | dict[str, Any]:
        import anthropic

        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = self._system_blocks(system)
        try:
            if isinstance(json_schema, type) and issubclass(json_schema, BaseModel):
                resp = await client.messages.parse(output_format=json_schema, **kwargs)
                self._check_stop(resp)
                parsed = resp.parsed_output
                if parsed is None:
                    return validate_output(parse_json_text(self._text(resp)), json_schema)
                return parsed.model_dump(mode="json")
            if json_schema:
                try:
                    resp = await client.messages.create(
                        output_config={"format": {"type": "json_schema", "schema": json_schema}}, **kwargs
                    )
                except anthropic.BadRequestError:
                    # e.g. a platform without structured outputs: fall back to prompting for JSON
                    kwargs["messages"][0]["content"] = _json_prompt(prompt, json_schema)
                    resp = await client.messages.create(**kwargs)
                self._check_stop(resp)
                return parse_json_text(self._text(resp))
            resp = await client.messages.create(**kwargs)
            self._check_stop(resp)
            return self._text(resp)
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Claude API error ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"Could not reach the Claude API: {exc}") from exc

    @staticmethod
    def _text(resp: Any) -> str:
        return "".join(b.text for b in resp.content if b.type == "text")

    @staticmethod
    def _check_stop(resp: Any) -> None:
        if resp.stop_reason == "refusal":
            raise ProviderError("Claude declined this request.")
        if resp.stop_reason == "max_tokens":
            raise ProviderError("The response was cut off (max_tokens). Try a smaller request.")


def _json_prompt(prompt: str, schema: dict[str, Any]) -> str:
    return (
        f"{prompt}\n\nRespond with ONLY a JSON object (no prose, no code fences) matching this JSON schema:\n"
        f"{json.dumps(schema)}"
    )


# ---------------------------------------------------------------------------
# Claude Code subscription (claude-agent-sdk + local `claude` CLI)
# ---------------------------------------------------------------------------

_DISALLOWED = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch", "Task"]


class ClaudeCodeProvider(LLMProvider):
    name = "claude-code"

    def _sdk(self):
        try:
            import claude_agent_sdk as sdk
        except ImportError as exc:
            raise ProviderError("claude-code provider needs `uv sync --extra claude-code` (claude-agent-sdk).") from exc
        return sdk

    @staticmethod
    def _cwd() -> Path:
        d = ROOT / "data" / "agent-cwd"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def status(self) -> dict[str, Any]:
        import shutil

        try:
            self._sdk()
        except ProviderError as exc:
            return {"provider": self.name, "model": self.model, "available": False, "detail": str(exc)}
        cli = shutil.which("claude")
        if not cli:
            return {
                "provider": self.name,
                "model": self.model,
                "available": False,
                "detail": "The `claude` CLI is not on PATH (install Claude Code and run `claude` once to log in).",
            }
        return {"provider": self.name, "model": self.model, "available": True, "detail": f"Claude Code CLI at {cli}"}

    def _options(self, sdk, system: str | None, *, mcp_server=None, tool_names=(), max_turns=MAX_TURNS, resume=None):
        kwargs: dict[str, Any] = {
            "system_prompt": system or "You are a helpful assistant.",
            "disallowed_tools": list(_DISALLOWED),
            "permission_mode": "bypassPermissions",
            "max_turns": max_turns,
            "cwd": str(self._cwd()),
            "setting_sources": [],
        }
        if self.settings.llm_model and self.settings.llm_model != "claude-opus-5-5":
            kwargs["model"] = self.settings.llm_model
        if mcp_server is not None:
            kwargs["mcp_servers"] = {"hl": mcp_server}
            kwargs["allowed_tools"] = [f"mcp__hl__{n}" for n in tool_names]
        if resume:
            kwargs["resume"] = resume
        return sdk.ClaudeAgentOptions(**kwargs)

    def _mcp_tools(self, sdk, tools: list[ToolSpec], user_id: str | None):
        wrapped = []
        for spec in tools:

            def make(spec: ToolSpec):
                async def handler(args: dict[str, Any]) -> dict[str, Any]:
                    outcome = await asyncio.to_thread(execute, spec, user_id, args or {})
                    out: dict[str, Any] = {"content": [{"type": "text", "text": outcome.as_text()}]}
                    if not outcome.ok:
                        out["is_error"] = True
                    return out

                return sdk.tool(spec.name, spec.description, spec.input_schema)(handler)

            wrapped.append(make(spec))
        return wrapped

    async def run_tools(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        on_event: OnEvent = None,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        max_turns: int = MAX_TURNS,
    ) -> AgentResult:
        sdk = self._sdk()
        server = sdk.create_sdk_mcp_server(name="hyperlane", version="1.0.0", tools=self._mcp_tools(sdk, tools, user_id))
        options = self._options(
            sdk, system, mcp_server=server, tool_names=[t.name for t in tools], max_turns=max_turns, resume=session_id
        )
        options.include_partial_messages = True

        prompt = last_user_text(messages)
        if not session_id and len(messages) > 1:
            prompt = (
                "Earlier conversation (for context):\n" + text_of_messages(messages[:-1]) + "\n\nNew message:\n" + prompt
            )

        result = AgentResult(session_id=session_id)
        text_parts: list[str] = []
        streamed = ""
        call_names: dict[str, str] = {}
        summaries: dict[str, str] = {}
        result.raw_messages.append({"role": "user", "content": [{"type": "text", "text": last_user_text(messages)}]})
        try:
            async for message in sdk.query(prompt=prompt, options=options):
                if isinstance(message, sdk.StreamEvent):
                    ev = message.event or {}
                    if ev.get("type") == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
                        delta = ev["delta"].get("text", "")
                        if delta and message.parent_tool_use_id is None:
                            streamed += delta
                            await _emit(on_event, {"type": "text", "delta": delta})
                elif isinstance(message, sdk.AssistantMessage):
                    if message.parent_tool_use_id is not None:
                        continue
                    blocks: list[dict[str, Any]] = []
                    for block in message.content:
                        if isinstance(block, sdk.TextBlock):
                            if block.text.strip():
                                text_parts.append(block.text)
                                if not streamed:
                                    await _emit(on_event, {"type": "text", "delta": block.text})
                                blocks.append({"type": "text", "text": block.text})
                        elif isinstance(block, sdk.ToolUseBlock):
                            if not block.name.startswith("mcp__hl__"):
                                continue  # CLI-internal tools (e.g. ToolSearch) are not ours to show
                            name = block.name.removeprefix("mcp__hl__")
                            call_names[block.id] = name
                            blocks.append({"type": "tool_use", "id": block.id, "name": name, "input": block.input})
                            await _emit(on_event, {"type": "tool_call", "id": block.id, "name": name, "input": block.input})
                    streamed = ""
                    if blocks:
                        result.raw_messages.append({"role": "assistant", "content": blocks})
                elif isinstance(message, sdk.UserMessage):
                    content = message.content if isinstance(message.content, list) else []
                    results: list[dict[str, Any]] = []
                    for block in content:
                        if isinstance(block, sdk.ToolResultBlock):
                            if block.tool_use_id not in call_names:
                                continue
                            name = call_names[block.tool_use_id]
                            body = block.content
                            if isinstance(body, list):
                                body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                            summary = _summary_from_text(str(body or ""))
                            summaries[block.tool_use_id] = summary
                            ok = not bool(block.is_error)
                            results.append(
                                {"type": "tool_result", "tool_use_id": block.tool_use_id, "content": str(body or "")[:4000]}
                            )
                            await _emit(
                                on_event,
                                {"type": "tool_result", "id": block.tool_use_id, "name": name, "summary": summary, "ok": ok},
                            )
                    if results:
                        result.raw_messages.append({"role": "user", "content": results})
                elif isinstance(message, sdk.ResultMessage):
                    result.session_id = message.session_id or result.session_id
                    result.stop_reason = message.stop_reason or ("error" if message.is_error else "end_turn")
                    if message.usage:
                        result.usage = {
                            "input_tokens": int(message.usage.get("input_tokens", 0) or 0),
                            "output_tokens": int(message.usage.get("output_tokens", 0) or 0),
                        }
                    if message.is_error:
                        result.error = message.result or "Claude Code returned an error."
                    elif not text_parts and message.result:
                        text_parts.append(message.result)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Claude Code failed: {exc.__class__.__name__}: {exc}") from exc

        for tu_id, name in call_names.items():
            result.tool_calls.append(
                {"id": tu_id, "name": name, "input": None, "result_summary": summaries.get(tu_id, ""), "ok": True}
            )
        # fill inputs from raw messages (keeps the summary shape identical to the API path)
        inputs = {
            b["id"]: b.get("input")
            for m in result.raw_messages
            if m["role"] == "assistant"
            for b in m["content"]
            if b.get("type") == "tool_use"
        }
        for call in result.tool_calls:
            call["input"] = inputs.get(call["id"])
        result.text = "\n\n".join(p.strip() for p in text_parts if p.strip())
        return result

    async def complete(
        self,
        system: str | None,
        prompt: str,
        *,
        json_schema: dict[str, Any] | type[BaseModel] | None = None,
        max_tokens: int = MAX_TOKENS,
    ) -> str | dict[str, Any]:
        sdk = self._sdk()
        schema = schema_of(json_schema)
        text_prompt = _json_prompt(prompt, schema) if schema else prompt
        options = self._options(sdk, system, max_turns=1)
        parts: list[str] = []
        final: str | None = None
        try:
            async for message in sdk.query(prompt=text_prompt, options=options):
                if isinstance(message, sdk.AssistantMessage):
                    for block in message.content:
                        if isinstance(block, sdk.TextBlock):
                            parts.append(block.text)
                elif isinstance(message, sdk.ResultMessage):
                    if message.is_error:
                        raise ProviderError(message.result or "Claude Code returned an error.")
                    final = message.result
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Claude Code failed: {exc.__class__.__name__}: {exc}") from exc
        text = "\n".join(parts).strip() or (final or "")
        if schema:
            return validate_output(parse_json_text(text), json_schema)
        return text


def _summary_from_text(text: str) -> str:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text[:200]
    from .tools import summarize

    return summarize("", data)


# ---------------------------------------------------------------------------
# Stub (tests / no provider)
# ---------------------------------------------------------------------------


class StubProvider(LLMProvider):
    """Deterministic stand-in. Echoes structure, calls `search_items` once, fills schemas minimally."""

    name = "none"

    def status(self) -> dict[str, Any]:
        return {
            "provider": "none",
            "model": "stub",
            "available": False,
            "detail": "No Claude provider configured (set HYPERLANE_LLM_PROVIDER in .env)",
        }

    async def run_tools(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        on_event: OnEvent = None,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        max_turns: int = MAX_TURNS,
    ) -> AgentResult:
        result = AgentResult(stop_reason="end_turn", usage={"input_tokens": 0, "output_tokens": 0})
        user_text = last_user_text(messages)
        search = next((t for t in tools if t.name == "search_items"), None)
        summary = ""
        if search is not None:
            tu_id = "stub-tool-1"
            tool_input = {"query": user_text[:60]}
            await _emit(on_event, {"type": "tool_call", "id": tu_id, "name": search.name, "input": tool_input})
            outcome = await asyncio.to_thread(execute, search, user_id, tool_input)
            summary = outcome.summary
            await _emit(
                on_event,
                {"type": "tool_result", "id": tu_id, "name": search.name, "summary": summary, "ok": outcome.ok},
            )
            result.tool_calls.append(
                {"id": tu_id, "name": search.name, "input": tool_input, "result_summary": summary, "ok": outcome.ok}
            )
            result.raw_messages.append(
                {"role": "assistant", "content": [{"type": "tool_use", "id": tu_id, "name": search.name, "input": tool_input}]}
            )
            result.raw_messages.append(
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tu_id, "content": outcome.as_text()}]}
            )
        text = f"**Stub agent** (no Claude provider configured). You said: {user_text.strip()[:200]}"
        if summary:
            text += f"\n\nSearch found: {summary}."
        for chunk in (text[: len(text) // 2], text[len(text) // 2 :]):
            await _emit(on_event, {"type": "text", "delta": chunk})
        result.raw_messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
        result.text = text
        return result

    async def complete(
        self,
        system: str | None,
        prompt: str,
        *,
        json_schema: dict[str, Any] | type[BaseModel] | None = None,
        max_tokens: int = MAX_TOKENS,
    ) -> str | dict[str, Any]:
        schema = schema_of(json_schema)
        if schema is None:
            first = prompt.strip().splitlines()[0] if prompt.strip() else ""
            return f"Stub: {first[:160]}"
        title = schema.get("title", "")
        data = stub_for_schema(title, schema, prompt)
        return validate_output(data, json_schema)


def stub_for_schema(title: str, schema: dict[str, Any], prompt: str) -> dict[str, Any]:
    """Deterministic, schema-aware fake objects used by tests and by `provider=none` installs."""
    if title == "IntakeAnalysis":
        m = re.search(r"Replies from requester:\s*(\d+)", prompt)
        replies = int(m.group(1)) if m else 0
        subject = (re.search(r"Subject:\s*(.+)", prompt) or [None, "the request"])[1].strip()
        confidence = 0.4 if replies == 0 else 0.9
        return {
            "problem": f"Stakeholder asked about: {subject}",
            "outcome": "A clear, deliverable slice of work exists in the backlog.",
            "users": "Requester and their team",
            "scope_in": [subject],
            "scope_out": [],
            "acceptance": ["Given the request is implemented, when the requester reviews it, then it meets the ask."],
            "constraints": [],
            "priority": "medium",
            "urgency": "normal",
            "open_questions": [] if replies else ["What outcome would make this a success?", "Who are the users?"],
            "confidence": confidence,
            "out_of_scope": False,
            "proposed_items": [
                {
                    "type": "story",
                    "title": subject[:120],
                    "description": "Drafted by the stub intake agent.",
                    "points": 3,
                    "acceptance_criteria": "Given … when … then …",
                }
            ],
            "summary": f"Request about {subject}; confidence {confidence:.0%}.",
        }
    if title == "BacklogDraft":
        goal = (re.search(r"Request:\s*(.+)", prompt) or [None, "the goal"])[1].strip()[:80]
        thin = len(goal) < 12
        types = re.search(r"Type hierarchy \(top to leaf\):\s*(.+)", prompt)
        levels = [t.strip() for t in types.group(1).split(">")] if types else ["epic", "feature", "story"]
        top, mid, leaf = (levels + ["story", "story"])[:3] if len(levels) >= 3 else (levels[0], levels[-1], levels[-1])
        return {
            "summary": f"Draft backlog for: {goal}",
            "questions": ["Could you tell me more about the goal and who it's for?"] if thin else [],
            "items": [
                {"temp_id": "e1", "parent_temp_id": None, "type": top, "title": f"{goal}", "description": "Epic drafted by stub.", "points": None, "priority": "high", "labels": []},
                {"temp_id": "f1", "parent_temp_id": "e1", "type": mid, "title": f"{goal}: core flow", "description": "Feature drafted by stub.", "points": None, "priority": "high", "labels": []},
                {"temp_id": "s1", "parent_temp_id": "f1", "type": leaf, "title": f"As a user I can start {goal}", "description": "Story drafted by stub.", "acceptance_criteria": "Given … when … then …", "points": 3, "priority": "medium", "labels": []},
                {"temp_id": "s2", "parent_temp_id": "f1", "type": leaf, "title": f"As a user I can finish {goal}", "description": "Story drafted by stub.", "acceptance_criteria": "Given … when … then …", "points": 5, "priority": "medium", "labels": []},
            ],
        }
    if title == "ColumnMapping":
        return {"mapping": {}, "notes": ["Stub provider: heuristic mapping kept as-is."]}
    return _minimal_for_schema(schema, schema.get("$defs", {}))


def _minimal_for_schema(schema: dict[str, Any], defs: dict[str, Any]) -> Any:
    if "$ref" in schema:
        return _minimal_for_schema(defs.get(schema["$ref"].rsplit("/", 1)[-1], {}), defs)
    if "anyOf" in schema:
        options = [o for o in schema["anyOf"] if o.get("type") != "null"]
        return _minimal_for_schema(options[0], defs) if options else None
    if "default" in schema:
        return schema["default"]
    t = schema.get("type")
    if t == "object":
        return {k: _minimal_for_schema(v, defs) for k, v in (schema.get("properties") or {}).items()}
    if t == "array":
        return []
    if t == "string":
        return schema["enum"][0] if schema.get("enum") else ""
    if t == "number":
        return 0.0
    if t == "integer":
        return 0
    if t == "boolean":
        return False
    return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_provider: LLMProvider | None = None
_provider_key: tuple[str, str] | None = None


def get_provider(settings: Settings | None = None) -> LLMProvider:
    global _provider, _provider_key
    settings = settings or get_settings()
    key = (settings.llm_provider, settings.llm_model)
    if _provider is not None and _provider_key == key:
        return _provider
    kind = (settings.llm_provider or "none").lower()
    if kind == "anthropic":
        _provider = AnthropicProvider(settings)
    elif kind == "bedrock":
        _provider = AnthropicProvider(settings, bedrock=True)
    elif kind in ("claude-code", "claude_code", "claudecode"):
        _provider = ClaudeCodeProvider(settings)
    else:
        if kind not in ("none", "stub", ""):
            log.warning("Unknown HYPERLANE_LLM_PROVIDER=%r; using the stub provider", settings.llm_provider)
        _provider = StubProvider(settings)
    _provider_key = key
    return _provider


def reset_provider() -> None:
    global _provider, _provider_key
    _provider = None
    _provider_key = None
