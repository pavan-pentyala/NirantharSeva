"""drop the toy model — Phase 4.3

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-20

D1/D7 (docs/PHASE2_PLAN.md, ADR-005): the toy model was frozen scaffolding
from Phase 1, kept alive deliberately through Phase 2-4.2 so the sync
engine (push/pull, outbox, conflict handling) had something working to
build against before the real referral domain existed, and so the fault
tests (E4's evidence) had a stable, trivial harness to drive while the real
screens were still being built. `docs/PHASE4_PLAN.md`'s P4.3 names this
migration as exactly where that exception ends.

event_seq (migration 0003) is untouched by this migration — it was
deliberately never OWNED BY toy_event, for exactly this moment: dropping
toy_event must not cascade-drop the sequence referral_event still uses.

downgrade() restores toy/toy_event as they existed immediately before this
migration (seq defaulting from the shared event_seq, per migration 0003's
ALTER) — not migration 0002's original standalone-autoincrement shape,
since downgrade only has to reverse this migration, not replay history.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("toy_event")
    op.drop_table("toy")


def downgrade() -> None:
    op.create_table(
        "toy",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("value", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("run_id", sa.Text, nullable=True),
    )

    op.create_table(
        "toy_event",
        sa.Column(
            "seq",
            sa.BigInteger,
            primary_key=True,
            autoincrement=False,
            server_default=sa.text("nextval('event_seq')"),
        ),
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
    op.create_index("ix_toy_event_toy_id_lamport", "toy_event", ["toy_id", "lamport"])
