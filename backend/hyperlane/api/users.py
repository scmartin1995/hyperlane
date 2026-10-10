"""People / profiles."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import User
from ..schemas.common import UserOut
from ..schemas.core import UserIn, UserPatch
from ..services import users as svc
from ..services.auth import DB, CurrentUser, OptionalUser
from .auth import user_out

router = APIRouter(prefix="/users", tags=["users"])


def _get(db, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


@router.get("", response_model=list[UserOut])
def list_users(db: DB, active: bool | None = None):
    return [user_out(u) for u in svc.list_users(db, active=active)]


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserIn, db: DB, _: OptionalUser):
    """Works without a session so the very first profile can be created on first run."""
    return user_out(svc.create_user(db, body.model_dump(exclude_unset=True)))


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: str, db: DB):
    return user_out(_get(db, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserPatch, db: DB, me: CurrentUser):
    return user_out(svc.update_user(db, _get(db, user_id), body.model_dump(exclude_unset=True), me))


@router.delete("/{user_id}", response_model=UserOut)
def deactivate_user(user_id: str, db: DB, me: CurrentUser):
    return user_out(svc.deactivate_user(db, _get(db, user_id), me))
