"""Configuration, read only from environment variables."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from flask import current_app

PROVIDERS = ("stripe", "mock")


class ConfigError(RuntimeError):
    """Raised when the environment is missing or has invalid settings."""


def normalize_database_url(url: str) -> str:
    """Make plain postgres:// and postgresql:// URLs use the psycopg 3 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    cors_origins: list[str]
    hold_minutes: int
    tourist_tax_per_person_night: Decimal
    payment_provider: str
    stripe_secret_key: str | None
    stripe_webhook_secret: str | None
    testing: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, testing: bool = False) -> Settings:
        database_url = env.get("DATABASE_URL", "").strip()
        if not database_url:
            raise ConfigError("DATABASE_URL is required")

        jwt_secret = env.get("JWT_SECRET", "").strip()
        if not jwt_secret:
            if not testing:
                raise ConfigError("JWT_SECRET is required")
            jwt_secret = secrets.token_hex(32)

        try:
            hold_minutes = int(env.get("HOLD_MINUTES", "15") or "15")
        except ValueError as exc:
            raise ConfigError("HOLD_MINUTES must be an integer") from exc
        if hold_minutes < 1:
            raise ConfigError("HOLD_MINUTES must be >= 1")

        try:
            tax = Decimal(env.get("TOURIST_TAX_PER_PERSON_NIGHT", "15.00") or "15.00")
        except InvalidOperation as exc:
            raise ConfigError("TOURIST_TAX_PER_PERSON_NIGHT must be a decimal") from exc
        if tax < 0:
            raise ConfigError("TOURIST_TAX_PER_PERSON_NIGHT must be >= 0")

        stripe_key = env.get("STRIPE_SECRET_KEY", "").strip() or None
        provider = env.get("PAYMENT_PROVIDER", "").strip().lower() or (
            "stripe" if stripe_key else "mock"
        )
        if provider not in PROVIDERS:
            raise ConfigError(f"PAYMENT_PROVIDER must be one of {PROVIDERS}")
        if provider == "stripe" and not stripe_key:
            raise ConfigError("STRIPE_SECRET_KEY is required when PAYMENT_PROVIDER=stripe")

        origins = [o.strip() for o in env.get("CORS_ORIGINS", "").split(",") if o.strip()]
        return cls(
            database_url=normalize_database_url(database_url),
            jwt_secret=jwt_secret,
            cors_origins=origins,
            hold_minutes=hold_minutes,
            tourist_tax_per_person_night=tax,
            payment_provider=provider,
            stripe_secret_key=stripe_key,
            stripe_webhook_secret=env.get("STRIPE_WEBHOOK_SECRET", "").strip() or None,
            testing=testing,
        )


def get_settings() -> Settings:
    settings: Settings = current_app.config["SETTINGS"]
    return settings
