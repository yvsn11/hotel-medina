from datetime import timedelta
from decimal import Decimal

import pytest
from flask import Flask
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import create_app
from app.config import ConfigError, Settings, normalize_database_url
from app.models import Booking, Rate, Role, Room, RoomType, User
from app.services import bookings
from app.services.seed import DEMO_PASSWORD
from tests.conftest import FIXED_NOW, TEST_DATABASE_URL, add_user, make_app, stay
from tests.test_bookings_service import book


def count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_seed_creates_exactly_the_demo_data_and_is_idempotent(app: Flask, session: Session) -> None:
    runner = app.test_cli_runner()
    first = runner.invoke(args=["seed"])
    assert first.exit_code == 0, first.output
    assert "room_types=3, rooms=8, rates=6, users=2" in first.output
    snapshot = (
        count(session, RoomType),
        count(session, Room),
        count(session, Rate),
        count(session, User),
    )
    assert snapshot == (3, 8, 6, 2)

    second = runner.invoke(args=["seed"])
    assert second.exit_code == 0 and "room_types=0, rooms=0, rates=0, users=0" in second.output
    session.expire_all()
    assert (
        count(session, RoomType),
        count(session, Room),
        count(session, Rate),
        count(session, User),
    ) == snapshot

    rooms = {
        (r.number, r.room_type.label, r.room_type.base_price, r.room_type.capacity)
        for r in session.scalars(select(Room))
    }
    assert rooms == {
        *((n, "Standard", Decimal("700.00"), 2) for n in ("101", "102", "103", "104")),
        *((n, "Deluxe", Decimal("1100.00"), 3) for n in ("201", "202", "203")),
        ("301", "Riad Suite", Decimal("2200.00"), 4),
    }
    rates = {
        (
            r.room_type.label if hasattr(r, "room_type") else r.room_type_id,
            r.season.lower,
            r.season.upper,
            r.price,
        )
        for r in session.scalars(select(Rate))
    }
    assert len(rates) == 6
    standard = session.scalars(select(RoomType).where(RoomType.label == "Standard")).one()
    prices = session.execute(
        select(Rate.season, Rate.price)
        .where(Rate.room_type_id == standard.id)
        .order_by(Rate.season)
    ).all()
    assert [(s.lower.isoformat(), s.upper.isoformat(), p) for s, p in prices] == [
        ("2026-03-01", "2026-06-01", Decimal("875.00")),
        ("2026-09-01", "2026-11-01", Decimal("875.00")),
    ]


def test_seeded_accounts_can_log_in(app: Flask, client) -> None:  # type: ignore[no-untyped-def]
    app.test_cli_runner().invoke(args=["seed"])
    for email, role in (("guest@demo.test", "guest"), ("staff@demo.test", "staff")):
        res = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
        assert res.status_code == 200 and res.get_json()["user"]["role"] == role


def test_seed_does_not_touch_existing_changes(app: Flask, session: Session) -> None:
    runner = app.test_cli_runner()
    runner.invoke(args=["seed"])
    standard = session.scalars(select(RoomType).where(RoomType.label == "Standard")).one()
    standard.base_price = Decimal("800")
    session.commit()
    runner.invoke(args=["seed"])
    session.expire_all()
    assert session.get(RoomType, standard.id).base_price == Decimal("800.00")  # type: ignore[union-attr]


def test_expire_holds_command(app: Flask, session: Session, catalog: dict[str, RoomType]) -> None:
    import app.clock as clock_module

    user = add_user(session, "cli@example.com", Role.GUEST)
    start, end = stay(10, 2)
    fresh = book(session, user, catalog["Standard"], start, end).booking
    old = book(session, user, catalog["Standard"], start, end).booking
    old.expires_at = clock_module.utcnow() - timedelta(minutes=1)
    session.commit()
    fresh_id, old_id = fresh.id, old.id

    out = app.test_cli_runner().invoke(args=["expire-holds"])
    assert out.exit_code == 0 and "expired 1 booking(s)" in out.output
    session.expire_all()
    assert session.get(Booking, old_id).status == "EXPIRED"  # type: ignore[union-attr]
    assert session.get(Booking, fresh_id).status == "PENDING"  # type: ignore[union-attr]
    assert bookings is not None and FIXED_NOW is not None


# ---- configuration ---------------------------------------------------------------------------

BASE_ENV = {"DATABASE_URL": "postgresql://u:p@h/db", "JWT_SECRET": "s3cret"}


def test_database_urls_are_normalized_to_psycopg3() -> None:
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    already = "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url(already) == already
    assert Settings.from_env(BASE_ENV).database_url == "postgresql+psycopg://u:p@h/db"


def test_defaults() -> None:
    s = Settings.from_env(BASE_ENV)
    assert s.hold_minutes == 15
    assert s.tourist_tax_per_person_night == Decimal("15.00")
    assert s.payment_provider == "mock" and s.cors_origins == []


def test_payment_provider_defaults_to_stripe_when_a_key_is_set() -> None:
    assert (
        Settings.from_env({**BASE_ENV, "STRIPE_SECRET_KEY": "sk_test_1"}).payment_provider
        == "stripe"
    )
    explicit = Settings.from_env(
        {**BASE_ENV, "STRIPE_SECRET_KEY": "sk_test_1", "PAYMENT_PROVIDER": "mock"}
    )
    assert explicit.payment_provider == "mock"


def test_cors_origins_are_split_and_trimmed() -> None:
    s = Settings.from_env({**BASE_ENV, "CORS_ORIGINS": " http://a.test, http://b.test ,"})
    assert s.cors_origins == ["http://a.test", "http://b.test"]


@pytest.mark.parametrize(
    "env",
    [
        {"JWT_SECRET": "x"},  # no database
        {"DATABASE_URL": "postgresql://h/db"},  # no JWT secret outside tests
        {**BASE_ENV, "PAYMENT_PROVIDER": "paypal"},
        {**BASE_ENV, "PAYMENT_PROVIDER": "stripe"},  # stripe without key
        {**BASE_ENV, "HOLD_MINUTES": "soon"},
        {**BASE_ENV, "HOLD_MINUTES": "0"},
        {**BASE_ENV, "TOURIST_TAX_PER_PERSON_NIGHT": "lots"},
        {**BASE_ENV, "TOURIST_TAX_PER_PERSON_NIGHT": "-1"},
    ],
)
def test_invalid_configuration_is_refused(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_jwt_secret_is_required_outside_testing_but_never_hardcoded() -> None:
    with pytest.raises(ConfigError, match="JWT_SECRET"):
        Settings.from_env({"DATABASE_URL": "postgresql://h/db"})
    a = Settings.from_env({"DATABASE_URL": "postgresql://h/db"}, testing=True).jwt_secret
    b = Settings.from_env({"DATABASE_URL": "postgresql://h/db"}, testing=True).jwt_secret
    assert a and b and a != b  # random per process, not a constant in the code


def test_create_app_reads_the_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL.replace("+psycopg", ""))
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ConfigError):
        create_app()
    monkeypatch.setenv("JWT_SECRET", "from-the-environment")
    built = create_app()
    assert built.config["SETTINGS"].jwt_secret == "from-the-environment"
    assert built.config["SETTINGS"].database_url.startswith("postgresql+psycopg://")
    assert built.debug is False and make_app().debug is False
