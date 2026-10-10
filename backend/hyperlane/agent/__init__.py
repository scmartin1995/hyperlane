"""Claude-powered agent: provider abstraction, BA chat, intake clarification, backlog builder, Excel import.

Sync helpers for the other slices (analytics, integrations):
    summarize_retro(retro, stats) -> str
    draft_capacity_insight(profile) -> list[str]
    quick(prompt, system=None) -> str
They never raise because a provider is missing: they fall back to simple heuristic text.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Coroutine
from typing import Any

from .prompts import CAPACITY_SYSTEM, RETRO_SYSTEM
from .provider import ProviderError, get_provider, parse_json_text

log = logging.getLogger(__name__)

__all__ = ["draft_capacity_insight", "get_provider", "quick", "summarize_retro"]


def _run_sync(coro: Coroutine[Any, Any, Any], timeout: float | None = 180) -> Any:
    """Run a coroutine from sync code, whether or not an event loop is already running in this thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # inside a running loop (e.g. an async route): hop to a fresh thread with its own loop
    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=runner, name="hl-agent-sync", daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise ProviderError("The agent took too long to answer.")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def quick(prompt: str, system: str | None = None) -> str:
    """One-shot answer (Slack `/hyperlane ask`, notifications). Heuristic text when no provider."""
    provider = get_provider()
    if not provider.available:
        return _heuristic_quick(prompt)
    try:
        out = _run_sync(provider.complete(system or "You are Hyperlane's concise project assistant.", prompt))
        return str(out)
    except ProviderError as exc:
        log.warning("quick() failed: %s", exc)
        return _heuristic_quick(prompt)
    except Exception:
        log.exception("quick() crashed")
        return _heuristic_quick(prompt)


def _heuristic_quick(prompt: str) -> str:
    first = prompt.strip().splitlines()[0] if prompt.strip() else ""
    return f"(agent offline) I noted: {first[:200]}"


def summarize_retro(retro: Any, stats: dict[str, Any] | None) -> str:
    """Markdown summary of a retro. `retro` is the ORM Retro (or a dict with the same keys)."""
    g = (lambda k: retro.get(k)) if isinstance(retro, dict) else (lambda k: getattr(retro, k, None))
    cols = {k: [e.get("text", "") if isinstance(e, dict) else str(e) for e in (g(k) or [])] for k in
            ("went_well", "improve", "kudos", "actions")}
    mood = g("mood") or {}
    avg_mood = round(sum(mood.values()) / len(mood), 1) if mood else None
    provider = get_provider()
    if provider.available:
        prompt = (
            f"Sprint stats: {json.dumps(stats or {}, default=str)[:2000]}\n"
            f"Average mood (1-5): {avg_mood}\n"
            f"Went well: {cols['went_well']}\nImprove: {cols['improve']}\nKudos: {cols['kudos']}\n"
            f"Actions: {cols['actions']}\nWrite the summary."
        )
        try:
            return str(_run_sync(provider.complete(RETRO_SYSTEM, prompt)))
        except ProviderError as exc:
            log.warning("retro summary fell back to heuristic: %s", exc)
        except Exception:
            log.exception("retro summary crashed")
    return _heuristic_retro(cols, stats or {}, avg_mood)


def _heuristic_retro(cols: dict[str, list[str]], stats: dict[str, Any], avg_mood: float | None) -> str:
    committed = stats.get("committed_points") or stats.get("committed")
    completed = stats.get("completed_points") or stats.get("completed")
    lines = ["## Lap debrief"]
    if committed is not None and completed is not None:
        try:
            pct = round(100 * float(completed) / float(committed)) if float(committed) else 0
            lines.append(f"Delivered **{completed}** of **{committed}** committed ({pct}%).")
        except (TypeError, ValueError):
            pass
    if avg_mood is not None:
        lines.append(f"Team mood: **{avg_mood}/5**.")
    for key, label in (("went_well", "Went well"), ("improve", "Improve"), ("kudos", "Kudos"), ("actions", "Actions")):
        if cols[key]:
            lines.append(f"\n**{label}**")
            lines.extend(f"- {t}" for t in cols[key][:6])
    if len(lines) == 1:
        lines.append("Nothing captured yet; add a few notes and generate again.")
    return "\n".join(lines)


def draft_capacity_insight(profile: Any) -> list[str]:
    """1-3 short coaching notes about a CapacityProfile (ORM object or dict)."""
    g = (lambda k, d=None: profile.get(k, d)) if isinstance(profile, dict) else (lambda k, d=None: getattr(profile, k, d))
    observed = int(g("sprints_observed", 0) or 0)
    avg = float(g("avg_points", 0.0) or 0.0)
    acc = float(g("commitment_accuracy", 1.0) or 1.0)
    std = float(g("stddev_points", 0.0) or 0.0)
    heuristic: list[str] = []
    if observed < 2:
        heuristic.append("Too early to call: fewer than two sprints observed.")
    else:
        if acc < 0.8:
            heuristic.append(f"Tends to over-commit (delivers ~{round(acc * 100)}% of planned); plan ~{round(avg)} pts.")
        elif acc > 1.15:
            heuristic.append(f"Sandbagging a little (delivers ~{round(acc * 100)}% of planned); there's headroom.")
        else:
            heuristic.append(f"Reliable: delivers close to plan, around {round(avg)} pts a sprint.")
        if avg and std / avg > 0.5:
            heuristic.append("Delivery swings a lot sprint to sprint; check for interrupts or unclear stories.")
    provider = get_provider()
    if not provider.available or observed < 2:
        return heuristic
    prompt = (
        f"Profile: sprints_observed={observed}, avg_points={avg:.1f}, stddev_points={std:.1f}, "
        f"commitment_accuracy={acc:.2f}, history={json.dumps(g('history', []) or [], default=str)[:1500]}"
    )
    try:
        out = _run_sync(provider.complete(CAPACITY_SYSTEM, prompt))
        data = parse_json_text(str(out))
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return data[:3] or heuristic
    except ProviderError as exc:
        log.warning("capacity insight fell back to heuristic: %s", exc)
    except Exception:
        log.exception("capacity insight crashed")
    return heuristic
