"""Hotel Medina API application factory."""

from __future__ import annotations

import os
from typing import Any

from flask import Flask

from app.config import Settings
from app.errors import register_error_handlers
from app.extensions import cors, db, migrate
from app.services.payments import build_provider


def _engine_options(testing: bool) -> dict[str, Any]:
    # Always talk UTF-8 to the server: psycopg 3 returns raw bytes for text columns when the
    # connection encoding is SQL_ASCII (the default of some hosted/local Postgres clusters).
    options: dict[str, Any] = {"connect_args": {"client_encoding": "UTF8"}}
    if testing:
        options.update(pool_size=20, max_overflow=40)
    else:
        options.update(pool_pre_ping=True)
    return options


def create_app(overrides: dict[str, Any] | None = None) -> Flask:
    """Build the app. Settings come from environment variables.

    `overrides` (env-var names, plus an optional `TESTING` flag) take precedence over
    `os.environ`; they exist for tests.
    """
    overrides = dict(overrides or {})
    testing = bool(overrides.pop("TESTING", False))
    env: dict[str, str] = {**os.environ, **{k: str(v) for k, v in overrides.items()}}
    settings = Settings.from_env(env, testing=testing)

    app = Flask(__name__, static_folder=None)
    app.config.update(
        SETTINGS=settings,
        TESTING=testing,
        DEBUG=False,
        JSON_SORT_KEYS=False,
        SQLALCHEMY_DATABASE_URI=settings.database_url,
        SQLALCHEMY_ENGINE_OPTIONS=_engine_options(testing),
    )
    app.json.sort_keys = False  # type: ignore[attr-defined]

    db.init_app(app)
    migrate.init_app(
        app,
        db,
        directory=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "migrations")),
    )
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": settings.cors_origins}},
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        max_age=600,
    )
    app.extensions["payment_provider"] = build_provider(
        settings.payment_provider, settings.stripe_secret_key
    )

    register_error_handlers(app)

    from app.cli import register_cli
    from app.routes import register_routes

    register_routes(app)
    register_cli(app)
    return app
