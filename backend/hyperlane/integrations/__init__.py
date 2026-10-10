"""Integrations: Slack (Socket Mode), Microsoft Teams (webhook), email intake (IMAP/SMTP), notification router.

Started by `main.lifespan` via `start_all(app)`; everything is a no-op unless configured in `.env`.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import get_settings
from ..services import scheduler
from ..services.events import bus
from . import email, router, slack, teams

log = logging.getLogger(__name__)

_subscribed = False
_jobs_registered = False


def start_all(app: Any = None) -> None:
    global _subscribed, _jobs_registered
    s = get_settings()
    if not _subscribed:
        bus.subscribe(router.handle)
        _subscribed = True
    if s.slack_enabled:
        slack.start()
    else:
        log.info("slack: not configured")
    if not _jobs_registered:
        if s.email_intake_enabled:
            scheduler.register_job(
                email.poll_inbox, trigger="interval", seconds=max(15, s.intake_poll_seconds), id="email-poll"
            )
            log.info("email intake: polling every %ss", s.intake_poll_seconds)
        if s.slack_bot_token or s.teams_enabled:
            scheduler.register_job(
                router.daily_digest, trigger="cron", hour=9, minute=0, id="daily-digest", timezone=_local_tz()
            )
            log.info("daily digest scheduled for 09:00 local")
        _jobs_registered = True


def stop_all() -> None:
    slack.stop()
    router.shutdown()


def status() -> dict[str, Any]:
    """Matches `IntegrationsStatus` in frontend/src/api/types.ts."""
    return {"slack": slack.status(), "teams": teams.status(), "email": email.status()}


def _local_tz() -> Any:
    try:
        from tzlocal import get_localzone

        return get_localzone()
    except ImportError:
        from datetime import datetime

        return datetime.now().astimezone().tzinfo


__all__ = ["email", "router", "slack", "start_all", "status", "stop_all", "teams"]
