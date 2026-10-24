"""Flask CLI commands: `seed` and `expire-holds` (`db upgrade` comes from Flask-Migrate)."""

from __future__ import annotations

import click
from flask import Flask

from app import clock
from app.extensions import get_session
from app.services import holds
from app.services.seed import seed


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_command() -> None:
        """Create the demo data (idempotent)."""
        created = seed(get_session())
        click.echo("seeded: " + ", ".join(f"{k}={v}" for k, v in created.items()))

    @app.cli.command("expire-holds")
    def expire_holds_command() -> None:
        """Release PENDING bookings whose hold has expired (run from cron)."""
        count = holds.expire_holds(get_session(), clock.utcnow())
        click.echo(f"expired {count} booking(s)")
