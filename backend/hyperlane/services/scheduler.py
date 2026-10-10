"""Tiny wrapper over APScheduler so any module can register background jobs at import time."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="UTC")
_pending: list[tuple[Callable[..., Any], dict[str, Any]]] = []


def register_job(fn: Callable[..., Any], **trigger_kwargs: Any) -> None:
    """register_job(fn, trigger="interval", seconds=60, id="email-poll")"""
    _pending.append((fn, trigger_kwargs))
    if _scheduler.running:
        _scheduler.add_job(fn, **trigger_kwargs)


def start() -> None:
    if _scheduler.running:
        return
    for fn, kw in _pending:
        _scheduler.add_job(fn, **kw)
    _scheduler.start()
    log.info("scheduler started with %d jobs", len(_pending))


def stop() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
