from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from psycopg.types.range import Range
from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import DATERANGE, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.catalog import Room
from app.models.user import User


class BookingStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


ACTIVE_STATUSES = (BookingStatus.PENDING.value, BookingStatus.CONFIRMED.value)


class PaymentStatus(StrEnum):
    REQUIRES_PAYMENT = "REQUIRES_PAYMENT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Booking(Base):
    """A stay. Overlap protection is the `no_overlapping_stays` exclusion constraint and
    the idempotency guarantee is the `uq_booking_idempotency` unique index (see migration).
    """

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    stay: Mapped[Range[date]] = mapped_column(DATERANGE)
    guests: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default=BookingStatus.PENDING.value)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="MAD")
    # Price breakdown frozen at booking time (additive column, not in the original contract).
    price: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()
    room: Mapped[Room] = relationship()
    payment: Mapped[Payment | None] = relationship(back_populates="booking", uselist=False)

    @property
    def check_in(self) -> date:
        assert self.stay.lower is not None
        return self.stay.lower

    @property
    def check_out(self) -> date:
        assert self.stay.upper is not None
        return self.stay.upper

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.REQUIRES_PAYMENT.value)
    provider: Mapped[str] = mapped_column(String(20))
    provider_ref: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    booking: Mapped[Booking] = relationship(back_populates="payment")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
