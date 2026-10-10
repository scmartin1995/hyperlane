"""People: dev profiles."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User
from .events import bus

ROLES = {"developer", "pm", "po", "designer", "qa", "lead", "stakeholder"}
_USER_FIELDS = {
    "name", "email", "role", "emoji", "color", "skills", "bio", "slack_user_id", "timezone",
    "hours_per_week", "focus_factor",
}  # fmt: skip


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "user"


def unique_handle(db: Session, base: str, *, exclude_id: str | None = None) -> str:
    base = slugify(base)[:50]
    candidate = base
    n = 2
    while True:
        stmt = select(User.id).where(User.handle == candidate)
        if exclude_id:
            stmt = stmt.where(User.id != exclude_id)
        if db.scalar(stmt) is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


def create_user(db: Session, data: dict[str, Any]) -> User:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    handle = unique_handle(db, data.get("handle") or name)
    email = (data.get("email") or None) or None
    if email and db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ValueError(f"email {email} is already used by another profile")
    user = User(name=name, handle=handle, email=email)
    for field in _USER_FIELDS - {"name", "email"}:
        if data.get(field) is not None:
            setattr(user, field, data[field])
    if data.get("preferences"):
        user.preferences = dict(data["preferences"])
    db.add(user)
    db.commit()
    bus.emit("user.created", entity_type="user", entity_id=user.id)
    return user


def update_user(db: Session, user: User, data: dict[str, Any], actor: User | None = None) -> User:
    for field in _USER_FIELDS:
        if field in data and data[field] is not None:
            if field == "name" and not str(data[field]).strip():
                raise ValueError("name cannot be empty")
            setattr(user, field, data[field])
    if "email" in data and data["email"] is None:
        user.email = None
    if data.get("handle"):
        user.handle = unique_handle(db, data["handle"], exclude_id=user.id)
    if data.get("preferences") is not None:
        user.preferences = {**(user.preferences or {}), **data["preferences"]}
    if data.get("is_active") is not None:
        user.is_active = bool(data["is_active"])
    db.commit()
    bus.emit("user.updated", entity_type="user", entity_id=user.id, actor_id=actor.id if actor else None)
    return user


def deactivate_user(db: Session, user: User, actor: User | None = None) -> User:
    return update_user(db, user, {"is_active": False}, actor)


def list_users(db: Session, *, active: bool | None = None) -> list[User]:
    stmt = select(User).order_by(User.is_active.desc(), User.name)
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))
    return list(db.scalars(stmt))
