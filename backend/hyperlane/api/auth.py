"""Profile picking + PIN + session cookie."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..db import utcnow
from ..models import User
from ..schemas.common import UserBrief, UserOut
from ..services.auth import COOKIE, MAX_AGE, DB, OptionalUser, check_pin, hash_pin, make_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    user_id: str
    pin: str | None = None


class SetPinIn(BaseModel):
    pin: str | None  # None clears


def user_out(u: User) -> UserOut:
    out = UserOut.model_validate(u)
    out.has_pin = bool(u.pin_hash)
    return out


@router.get("/profiles", response_model=list[UserBrief])
def profiles(db: DB):
    return db.query(User).filter(User.is_active.is_(True)).order_by(User.name).all()


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: DB):
    user = db.get(User, body.user_id)
    if user is None or not user.is_active:
        raise HTTPException(404, "Profile not found")
    if user.pin_hash and not check_pin(body.pin or "", user.pin_hash):
        raise HTTPException(403, "Wrong PIN")
    user.last_seen_at = utcnow()
    db.commit()
    response.set_cookie(COOKIE, make_token(user.id), max_age=MAX_AGE, httponly=True, samesite="lax")
    return user_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me", response_model=UserOut | None)
def me(user: OptionalUser, db: DB):
    if user is None:
        return None
    user.last_seen_at = utcnow()
    db.commit()
    return user_out(user)


@router.post("/pin", response_model=UserOut)
def set_pin(body: SetPinIn, user: OptionalUser, db: DB):
    if user is None:
        raise HTTPException(401, "Pick a profile first")
    user.pin_hash = hash_pin(body.pin) if body.pin else None
    db.commit()
    return user_out(user)
