"""Registration and login (no Flask)."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from app.errors import EmailTaken, Unauthorized
from app.models import Role, User

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Verified against when the email is unknown, so timing does not reveal which emails exist.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def register_user(
    session: Session, email: str, password: str, full_name: str, role: Role = Role.GUEST
) -> User:
    email = normalize_email(email)
    if session.scalars(select(User).where(User.email == email)).first() is not None:
        raise EmailTaken("This email is already registered")
    user = User(
        email=email, password_hash=hash_password(password), full_name=full_name, role=role.value
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:  # concurrent registration with the same email
        session.rollback()
        raise EmailTaken("This email is already registered") from exc
    return user


def authenticate(session: Session, email: str, password: str) -> User:
    user = session.scalars(select(User).where(User.email == normalize_email(email))).first()
    stored = user.password_hash if user is not None else _DUMMY_HASH
    valid = check_password_hash(stored, password)
    if user is None or not valid:
        raise Unauthorized("Invalid email or password")
    return user
