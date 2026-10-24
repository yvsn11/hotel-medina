"""Booking holds: PENDING bookings expire so the room is released."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus


def expire_holds(session: Session, now: datetime) -> int:
    """Mark every PENDING booking whose hold ended as EXPIRED. Returns how many.

    Rows locked by another transaction (e.g. a payment being confirmed) are skipped, and
    rows are locked in id order so concurrent sweeps never deadlock. Commits.
    """
    stale = (
        select(Booking.id)
        .where(
            Booking.status == BookingStatus.PENDING.value,
            Booking.expires_at.is_not(None),
            Booking.expires_at <= now,
        )
        .order_by(Booking.id)
        .with_for_update(skip_locked=True)
    )
    expired = session.scalars(
        update(Booking)
        .where(Booking.id.in_(stale))
        .values(status=BookingStatus.EXPIRED.value)
        .returning(Booking.id)
    ).all()
    session.commit()
    return len(expired)
