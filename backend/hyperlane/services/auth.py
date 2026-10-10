"""Identity: pick a profile, optionally confirm a PIN, get a signed cookie.

The server keeps no session state; the cookie is a signed user id (itsdangerous).
"""

from __future__ import annotations

from typing import Annotated

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User

COOKIE = "hl_session"
MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret, salt="hl-session")


def make_token(user_id: str) -> str:
    return _serializer().dumps({"uid": user_id})


def read_token(token: str) -> str | None:
    try:
        data = _serializer().loads(token, max_age=MAX_AGE)
        return data.get("uid")
    except BadSignature:
        return None


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def check_pin(pin: str, pin_hash: str | None) -> bool:
    if not pin_hash:
        return True
    try:
        return bcrypt.checkpw(pin.encode(), pin_hash.encode())
    except ValueError:
        return False


def optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    hl_session: Annotated[str | None, Cookie()] = None,
) -> User | None:
    token = hl_session or request.headers.get("x-hl-token")
    if not token:
        return None
    uid = read_token(token)
    if not uid:
        return None
    user = db.get(User, uid)
    if user is None or not user.is_active:
        return None
    return user


def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Pick a profile first")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
DB = Annotated[Session, Depends(get_db)]
