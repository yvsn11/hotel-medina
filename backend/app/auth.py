"""JWT creation/verification and the role-check decorator."""

from __future__ import annotations

import functools
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, ParamSpec, TypeVar

import jwt
from flask import g, request

from app import clock
from app.config import get_settings
from app.errors import Forbidden, Unauthorized
from app.extensions import db
from app.models import Role, User

TOKEN_TTL = timedelta(minutes=60)
ALGORITHM = "HS256"

P = ParamSpec("P")
R = TypeVar("R")


def create_token(user: User, secret: str, now: datetime | None = None) -> str:
    issued = now or clock.utcnow()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "iat": issued,
        "exp": issued + TOKEN_TTL,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str) -> dict[str, Any]:
    try:
        # Expiry is checked below against `clock.utcnow()` so tests can control time.
        claims: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "role"], "verify_exp": False, "verify_iat": False},
        )
        expires = float(claims["exp"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise Unauthorized("Invalid or expired token") from exc
    if expires <= clock.utcnow().timestamp():
        raise Unauthorized("Invalid or expired token")
    return claims


def current_user() -> User:
    user: User = g.current_user
    return user


def require_roles(*roles: Role) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Require a valid bearer token whose user (re-read from the database) has one of `roles`.

    With no roles, any authenticated user is accepted.
    """

    def decorator(view: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(view)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            header = request.headers.get("Authorization", "")
            scheme, _, token = header.partition(" ")
            if scheme.lower() != "bearer" or not token.strip():
                raise Unauthorized("Missing bearer token")
            claims = decode_token(token.strip(), get_settings().jwt_secret)
            try:
                user_id = int(claims["sub"])
            except ValueError as exc:
                raise Unauthorized("Invalid or expired token") from exc
            user = db.session.get(User, user_id)
            if user is None:
                raise Unauthorized("Unknown user")
            if roles and user.role not in {r.value for r in roles}:
                raise Forbidden("You do not have access to this resource")
            g.current_user = user
            return view(*args, **kwargs)

        return wrapper

    return decorator
