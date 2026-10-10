"""Microsoft Teams: outbound only, via an incoming-webhook URL.

Posts an Adaptive Card; if the webhook rejects it (older Office 365 connectors), falls back to the
legacy MessageCard format. Nothing touches the network unless TEAMS_WEBHOOK_URL (or a project
override) is set. Every attempt is written to `NotificationLog`.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import get_settings
from ._common import record_notification

log = logging.getLogger(__name__)

Facts = list[tuple[str, str]]


def build_adaptive_card(text: str, title: str | None = None, facts: Facts | None = None) -> dict[str, Any]:
    body: list[dict[str, Any]] = []
    if title:
        body.append({"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": title, "wrap": True})
    body.append({"type": "TextBlock", "text": text, "wrap": True})
    if facts:
        body.append({"type": "FactSet", "facts": [{"title": k, "value": v} for k, v in facts]})
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                },
            }
        ],
    }


def build_message_card(text: str, title: str | None = None, facts: Facts | None = None) -> dict[str, Any]:
    section: dict[str, Any] = {"text": text}
    if facts:
        section["facts"] = [{"name": k, "value": v} for k, v in facts]
    card: dict[str, Any] = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title or text[:100],
        "themeColor": "E4B963",
        "sections": [section],
    }
    if title:
        card["title"] = title
    return card


def post_card(
    text: str,
    title: str | None = None,
    facts: Facts | None = None,
    webhook: str | None = None,
    *,
    kind: str = "message",
    entity_type: str | None = None,
    entity_id: str | None = None,
    project_id: str | None = None,
) -> bool:
    """POST a card to the webhook. Returns True on success. Always logs (unless unconfigured)."""
    url = webhook or get_settings().teams_webhook_url
    if not url:
        log.warning("teams: not configured; dropping card %r", title or text[:40])
        return False
    ok, err = _send(url, text, title, facts)
    record_notification(
        channel="teams",
        target=_redact(url),
        kind=kind,
        body=(f"{title}\n{text}" if title else text),
        ok=ok,
        error=err,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        meta={"facts": list(facts or [])},
    )
    return ok


def _send(url: str, text: str, title: str | None, facts: Facts | None) -> tuple[bool, str | None]:
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return False, "httpx not installed"
    payloads = [
        ("adaptive", build_adaptive_card(text, title, facts)),
        ("messagecard", build_message_card(text, title, facts)),
    ]
    last: str | None = None
    for fmt, payload in payloads:
        try:
            resp = httpx.post(url, json=payload, timeout=15.0)
            if 200 <= resp.status_code < 300:
                return True, None
            last = f"{fmt}: HTTP {resp.status_code} {resp.text[:200]}"
            log.warning("teams webhook rejected %s payload: %s", fmt, last)
        except Exception as e:  # noqa: BLE001 - network/API errors are logged + recorded, never raised
            last = f"{fmt}: {e}"
            log.error("teams webhook error: %s", last)
            break  # network error: don't retry with the other format
    return False, last


def _redact(url: str) -> str:
    """Webhook URLs carry a secret: keep only the host for the log."""
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}/…"
    except ValueError:
        return "teams-webhook"


def test_connection() -> dict[str, Any]:
    if not get_settings().teams_webhook_url:
        return {"ok": False, "detail": "TEAMS_WEBHOOK_URL not set"}
    ok = post_card(
        "If you can read this, Hyperlane can reach this channel.",
        title="Hyperlane test card",
        facts=[("Status", "connected")],
        kind="test",
    )
    return {
        "ok": ok,
        "detail": "test card posted" if ok else "webhook rejected the card (see notification log)",
    }


def status() -> dict[str, Any]:
    s = get_settings()
    return {
        "enabled": s.teams_enabled,
        "detail": "incoming webhook configured" if s.teams_enabled else "not configured (TEAMS_WEBHOOK_URL)",
    }
