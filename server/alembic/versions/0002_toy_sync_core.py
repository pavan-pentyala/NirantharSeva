"""toy sync core — Phase 1.1

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-16

The toy model: one table, one integer field. This is the entire domain for
Phase 1 (plan §5.1) — thrown away once the real schema lands in Phase 2.

Timestamp columns have no server-side DEFAULT now(). They are written by the
application from the injected Clock (docs/decisions/ADR-001.md) so that
CLOCK_MODE=simulated experiment runs produce internally coherent timestamps.
A DB-side now() would bypass the simulated clock silently.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "toy",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("value", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("run_id", sa.Text, nullable=True),
    )

    op.create_table(
        "toy_event",
        sa.Column("seq", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("toy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_value", sa.Integer, nullable=True),
        sa.Column("new_value", sa.Integer, nullable=False),
        sa.Column("op_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("lamport", sa.BigInteger, nullable=False),
        sa.Column("device_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("server_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("run_id", sa.Text, nullable=True),
    )
    op.create_index("ix_toy_event_toy_id", "toy_event", ["toy_id"])
    # Speeds the lamport-order winner lookup in apply_operation (LWW register).
    op.create_index("ix_toy_event_toy_id_lamport", "toy_event", ["toy_id", "lamport"])

    op.create_table(
        "sync_receipt",
        sa.Column("op_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("result", sa.Text, nullable=False),
        sa.Column("detail", postgresql.JSONB, nullable=True),
        sa.Column("server_seq", sa.BigInteger, nullable=True),
    )

    op.create_table(
        "request_timing",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("endpoint", sa.Text, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("status", sa.Integer, nullable=False),
        sa.Column("duration_ms", sa.Numeric, nullable=False),
        sa.Column("run_id", sa.Text, nullable=True),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_request_timing_run_id", "request_timing", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_request_timing_run_id", table_name="request_timing")
    op.drop_table("request_timing")
    op.drop_table("sync_receipt")
    op.drop_index("ix_toy_event_toy_id_lamport", table_name="toy_event")
    op.drop_index("ix_toy_event_toy_id", table_name="toy_event")
    op.drop_table("toy_event")
    op.drop_table("toy")
