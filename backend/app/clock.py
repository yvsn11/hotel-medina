"""Single source of "now" for request handling (tests may monkeypatch `utcnow`)."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
