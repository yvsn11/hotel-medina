from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from psycopg.types.range import Range
from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import DATERANGE
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class RoomStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    MAINTENANCE = "MAINTENANCE"


class RoomType(Base):
    __tablename__ = "room_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    capacity: Mapped[int]

    rooms: Mapped[list[Room]] = relationship(back_populates="room_type")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)
    status: Mapped[str] = mapped_column(String(20), default=RoomStatus.AVAILABLE.value)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"))

    room_type: Mapped[RoomType] = relationship(back_populates="rooms")


class Rate(Base):
    """Seasonal price. The no-overlap guarantee is an exclusion constraint (see migration)."""

    __tablename__ = "rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"))
    season: Mapped[Range[date]] = mapped_column(DATERANGE)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
