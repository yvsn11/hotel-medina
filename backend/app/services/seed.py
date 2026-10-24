"""Idempotent demo data (see docs/api.md, "Demo data")."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from psycopg.types.range import Range
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Rate, Role, Room, RoomType, User
from app.services.pricing import quantize
from app.services.users import hash_password

DEMO_PASSWORD = "demo1234"  # noqa: S105 - public demo credentials, documented in the contract
HIGH_SEASON_MULTIPLIER = Decimal("1.25")
HIGH_SEASONS = (
    (date(2026, 3, 1), date(2026, 6, 1)),
    (date(2026, 9, 1), date(2026, 11, 1)),
)


@dataclass(frozen=True)
class TypeSpec:
    label: str
    description: str
    base_price: Decimal
    capacity: int
    rooms: tuple[str, ...]


ROOM_TYPES = (
    TypeSpec(
        "Standard",
        "Comfortable room with a double bed, zellige bathroom and courtyard view.",
        Decimal("700"),
        2,
        ("101", "102", "103", "104"),
    ),
    TypeSpec(
        "Deluxe",
        "Spacious room with a lounge corner, traditional woodwork and a private balcony.",
        Decimal("1100"),
        3,
        ("201", "202", "203"),
    ),
    TypeSpec(
        "Riad Suite",
        "Our signature suite: two levels, a private terrace and a fountain-side sitting room.",
        Decimal("2200"),
        4,
        ("301",),
    ),
)
DEMO_USERS = (
    ("guest@demo.test", "Demo Guest", Role.GUEST),
    ("staff@demo.test", "Demo Staff", Role.STAFF),
)


def seed(session: Session) -> dict[str, int]:
    """Create whatever demo data is missing. Returns how many rows were created."""
    created = {"room_types": 0, "rooms": 0, "rates": 0, "users": 0}
    for spec in ROOM_TYPES:
        room_type = session.scalars(select(RoomType).where(RoomType.label == spec.label)).first()
        if room_type is None:
            room_type = RoomType(
                label=spec.label,
                description=spec.description,
                base_price=spec.base_price,
                capacity=spec.capacity,
            )
            session.add(room_type)
            session.flush()
            created["room_types"] += 1
        for number in spec.rooms:
            if session.scalars(select(Room).where(Room.number == number)).first() is None:
                session.add(Room(number=number, room_type_id=room_type.id))
                created["rooms"] += 1
        for start, end in HIGH_SEASONS:
            season = Range(start, end, "[)")
            exists = session.scalars(
                select(Rate).where(Rate.room_type_id == room_type.id, Rate.season == season)
            ).first()
            if exists is None:
                price = quantize(spec.base_price * HIGH_SEASON_MULTIPLIER)
                session.add(Rate(room_type_id=room_type.id, season=season, price=price))
                created["rates"] += 1
    for email, name, role in DEMO_USERS:
        if session.scalars(select(User).where(User.email == email)).first() is None:
            session.add(
                User(
                    email=email,
                    full_name=name,
                    role=role.value,
                    password_hash=hash_password(DEMO_PASSWORD),
                )
            )
            created["users"] += 1
    session.commit()
    return created
