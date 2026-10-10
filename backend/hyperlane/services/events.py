"""In-process event bus.

Anything that changes data publishes an event; subscribers include the SSE stream
(live UI updates for everyone on the LAN) and the notification router (Slack/Teams).
Events never leave the machine unless an integration is explicitly configured.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..db import utcnow

log = logging.getLogger(__name__)


@dataclass
class Event:
    type: str  # e.g. "work_item.updated", "sprint.started", "comment.created", "action_item.created"
    project_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    actor_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=utcnow)

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type,
                "project_id": self.project_id,
                "entity_type": self.entity_type,
                "entity_id": self.entity_id,
                "actor_id": self.actor_id,
                "data": self.data,
                "at": self.at.isoformat(),
            },
            default=str,
        )


Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: list[Subscriber] = []
        self._queues: set[asyncio.Queue[Event]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, fn: Subscriber) -> None:
        self._subs.append(fn)

    def publish(self, event: Event) -> None:
        """Thread-safe: may be called from request handlers, Slack threads, or the scheduler."""
        for fn in list(self._subs):
            try:
                fn(event)
            except Exception:  # pragma: no cover
                log.exception("event subscriber failed for %s", event.type)
        loop = self._loop
        if loop is None:
            return
        with self._lock:
            queues = list(self._queues)
        for q in queues:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:  # loop closed
                pass

    def emit(self, type: str, **kw: Any) -> Event:
        ev = Event(type=type, **kw)
        self.publish(ev)
        return ev

    def listen(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=500)
        with self._lock:
            self._queues.add(q)
        return q

    def unlisten(self, q: asyncio.Queue[Event]) -> None:
        with self._lock:
            self._queues.discard(q)


bus = EventBus()
