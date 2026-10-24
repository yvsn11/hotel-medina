"""Test fixtures: a real PostgreSQL database, built by the Alembic migrations."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_migrate import upgrade
from psycopg.types.range import Range
from sqlalchemy import text
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from app import auth as auth_lib
from app import clock, create_app
from app.extensions import db
from app.models import Rate, Role, Room, RoomType, User

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/medina_test"
)
JWT_SECRET = "test-secret-" + "x" * 32
WEBHOOK_SECRET = "whsec_test_secret"
PASSWORD = "password123"
# One cheap hash shared by all fixture users (hashing is slow by design).
PASSWORD_HASH = generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000")

FIXED_NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
TABLES = "webhook_events, payments, bookings, rates, rooms, room_types, users"


def make_app(**overrides: str) -> Flask:
    config: dict[str, Any] = {
        "TESTING": True,
        "DATABASE_URL": TEST_DATABASE_URL,
        "JWT_SECRET": JWT_SECRET,
        "PAYMENT_PROVIDER": "mock",
        "STRIPE_SECRET_KEY": "",
        "STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "CORS_ORIGINS": "http://localhost:5173",
        "HOLD_MINUTES": "15",
        "TOURIST_TAX_PER_PERSON_NIGHT": "15.00",
    }
    config.update(overrides)
    return create_app(config)


@pytest.fixture(scope="session")
def app() -> Iterator[Flask]:
    """The app, on a database freshly built by running the real migrations."""
    flask_app = make_app()
    with flask_app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        upgrade()
        db.session.remove()
    yield flask_app
    with flask_app.app_context():
        db.engine.dispose()


@pytest.fixture(autouse=True)
def _clean_db(app: Flask) -> None:
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[datetime], None]:
    """Freeze `clock.utcnow()`; call the returned function to move time."""
    state = {"now": FIXED_NOW}
    monkeypatch.setattr(clock, "utcnow", lambda: state["now"])

    def set_now(value: datetime) -> None:
        state["now"] = value

    return set_now


@pytest.fixture
def session(app: Flask) -> Iterator[Session]:
    with app.app_context():
        yield db.session()
        db.session.remove()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def catalog(session: Session) -> dict[str, RoomType]:
    """Standard x4 (101-104, 700), Deluxe x3 (201-203, 1100), Suite x1 (301, 2200)."""
    types: dict[str, RoomType] = {}
    for label, price, capacity, numbers in (
        ("Standard", "700", 2, ["101", "102", "103", "104"]),
        ("Deluxe", "1100", 3, ["201", "202", "203"]),
        ("Suite", "2200", 4, ["301"]),
    ):
        rt = RoomType(
            label=label, description=f"{label} room", base_price=Decimal(price), capacity=capacity
        )
        session.add(rt)
        session.flush()
        for number in numbers:
            session.add(Room(number=number, room_type_id=rt.id))
        types[label] = rt
    session.commit()
    return types


def add_user(session: Session, email: str, role: Role = Role.GUEST) -> User:
    user = User(
        email=email, password_hash=PASSWORD_HASH, full_name=email.split("@")[0], role=role.value
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def guest(session: Session) -> User:
    return add_user(session, "guest@example.com")


@pytest.fixture
def other_guest(session: Session) -> User:
    return add_user(session, "other@example.com")


@pytest.fixture
def staff(session: Session) -> User:
    return add_user(session, "staff@example.com", Role.STAFF)


def token_for(user: User) -> str:
    return auth_lib.create_token(user, JWT_SECRET, now=FIXED_NOW)


def auth_headers(user: User, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user)}", **extra}


def add_rate(session: Session, room_type: RoomType, start: date, end: date, price: str) -> Rate:
    rate = Rate(room_type_id=room_type.id, season=Range(start, end, "[)"), price=Decimal(price))
    session.add(rate)
    session.commit()
    return rate


def stay(days_from_now: int, nights: int) -> tuple[date, date]:
    start = FIXED_NOW.date() + timedelta(days=days_from_now)
    return start, start + timedelta(days=nights)
