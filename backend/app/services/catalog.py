"""Back-office operations on rooms, room types and seasonal rates (no Flask)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import psycopg.errors
from psycopg.types.range import Range
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import InvalidState, NotFound, ValidationFailed
from app.models import Rate, Room, RoomType


def list_rooms(session: Session) -> list[Room]:
    return list(session.scalars(select(Room).order_by(Room.number)))


def get_room(session: Session, room_id: int) -> Room:
    room = session.get(Room, room_id)
    if room is None:
        raise NotFound("Room not found")
    return room


def get_room_type(session: Session, room_type_id: int) -> RoomType:
    room_type = session.get(RoomType, room_type_id)
    if room_type is None:
        raise NotFound("Room type not found")
    return room_type


def update_room(session: Session, room_id: int, changes: dict[str, Any]) -> Room:
    room = get_room(session, room_id)
    for field, value in changes.items():
        setattr(room, field, value)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise InvalidState("This room number is already used") from exc
    return room


def update_room_type(session: Session, room_type_id: int, changes: dict[str, Any]) -> RoomType:
    room_type = get_room_type(session, room_type_id)
    for field, value in changes.items():
        setattr(room_type, field, value)
    session.commit()
    return room_type


def list_rates(session: Session, room_type_id: int) -> list[Rate]:
    get_room_type(session, room_type_id)
    return list(
        session.scalars(select(Rate).where(Rate.room_type_id == room_type_id).order_by(Rate.season))
    )


def add_rate(session: Session, room_type_id: int, start: date, end: date, price: Decimal) -> Rate:
    get_room_type(session, room_type_id)
    if end <= start:
        raise ValidationFailed("end must be after start", {"fields": {"end": "not after start"}})
    rate = Rate(room_type_id=room_type_id, season=Range(start, end, "[)"), price=price)
    session.add(rate)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if isinstance(exc.orig, psycopg.errors.ExclusionViolation):
            raise InvalidState("This season overlaps an existing rate") from exc
        raise
    return rate
