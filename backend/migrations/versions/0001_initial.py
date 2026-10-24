"""initial schema with exclusion constraints

Revision ID: 0001
Revises:
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="guest"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('guest', 'staff')", name="ck_users_role"),
    )
    op.create_table(
        "room_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.CheckConstraint("base_price >= 0", name="ck_room_types_price"),
        sa.CheckConstraint("capacity >= 1", name="ck_room_types_capacity"),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(20), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="AVAILABLE"),
        sa.Column("room_type_id", sa.Integer(), sa.ForeignKey("room_types.id"), nullable=False),
        sa.CheckConstraint("status IN ('AVAILABLE', 'MAINTENANCE')", name="ck_rooms_status"),
    )
    op.create_index("ix_rooms_room_type_id", "rooms", ["room_type_id"])
    op.create_table(
        "rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_type_id", sa.Integer(), sa.ForeignKey("room_types.id"), nullable=False),
        sa.Column("season", postgresql.DATERANGE(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint("price >= 0", name="ck_rates_price"),
    )
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("stay", postgresql.DATERANGE(), nullable=False),
        sa.Column("guests", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("total", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="MAD"),
        sa.Column("price", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'CANCELLED', 'EXPIRED')", name="ck_bookings_status"
        ),
        sa.CheckConstraint("guests >= 1", name="ck_bookings_guests"),
        sa.CheckConstraint("NOT isempty(stay)", name="ck_bookings_stay_not_empty"),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="REQUIRES_PAYMENT"),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_ref", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('REQUIRES_PAYMENT', 'SUCCEEDED', 'FAILED')", name="ck_payments_status"
        ),
    )
    op.create_index("ix_payments_provider_ref", "payments", ["provider_ref"])
    op.create_table(
        "webhook_events",
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Database-level guarantees, exactly as in docs/api.md.
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT no_overlapping_stays
          EXCLUDE USING gist (room_id WITH =, stay WITH &&)
          WHERE (status IN ('PENDING', 'CONFIRMED'))
        """
    )
    op.execute(
        """
        ALTER TABLE rates ADD CONSTRAINT no_overlapping_rates
          EXCLUDE USING gist (room_type_id WITH =, season WITH &&)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_booking_idempotency ON bookings (user_id, idempotency_key)
          WHERE idempotency_key IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_booking_idempotency")
    op.execute("ALTER TABLE rates DROP CONSTRAINT IF EXISTS no_overlapping_rates")
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS no_overlapping_stays")
    for table in ("webhook_events", "payments", "bookings", "rates", "rooms", "room_types", "users"):
        op.drop_table(table)
    # btree_gist is left installed: it may be shared with other schemas.
