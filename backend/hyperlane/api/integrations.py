"""Integrations status/test endpoints + notification log + manual send."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from .. import integrations
from ..config import get_settings
from ..integrations import email as email_integration
from ..integrations import slack, teams
from ..models import NotificationLog
from ..schemas.common import NotificationLogOut
from ..services.auth import DB, CurrentUser

router = APIRouter(tags=["integrations"])


class SendIn(BaseModel):
    channel: Literal["slack", "teams"]
    target: str | None = None  # slack channel (#name or id) / teams webhook url
    text: str


@router.get("/integrations/status")
def integrations_status():
    return integrations.status()


@router.post("/integrations/test/{which}")
def integrations_test(which: Literal["slack", "teams", "email"]):
    if which == "slack":
        return slack.test_connection()
    if which == "teams":
        return teams.test_connection()
    return email_integration.test_connection()


@router.get("/notifications/log", response_model=list[NotificationLogOut])
def notifications_log(db: DB, limit: int = 50):
    limit = max(1, min(limit, 500))
    return (
        db.execute(select(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(limit))
        .scalars()
        .all()
    )


@router.post("/notifications/send")
def notifications_send(body: SendIn, user: CurrentUser):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "text is required")
    s = get_settings()
    if body.channel == "slack":
        if not s.slack_bot_token:
            raise HTTPException(400, "Slack is not configured (SLACK_BOT_TOKEN)")
        target = body.target or s.slack_default_channel
        if not target:
            raise HTTPException(400, "No Slack target: pass `target` or set SLACK_DEFAULT_CHANNEL")
        ts = slack.post_message(
            target,
            f"{text}\n_— {user.name} via Hyperlane_",
            kind="manual",
            entity_type="user",
            entity_id=user.id,
        )
        return {
            "ok": ts is not None,
            "detail": f"posted to {target}" if ts else "Slack rejected the message (see log)",
        }
    webhook = body.target or s.teams_webhook_url
    if not webhook:
        raise HTTPException(400, "Teams is not configured (TEAMS_WEBHOOK_URL)")
    ok = teams.post_card(
        text,
        title=f"{user.name} via Hyperlane",
        webhook=webhook,
        kind="manual",
        entity_type="user",
        entity_id=user.id,
    )
    return {"ok": ok, "detail": "card posted" if ok else "Teams webhook rejected the card (see log)"}
