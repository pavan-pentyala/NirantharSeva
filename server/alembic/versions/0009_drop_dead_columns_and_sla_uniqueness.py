"""Drop two dead columns, add sla_profile uniqueness — pre-Phase-9 audit

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-24

Pre-Phase-9 codebase audit found two columns that were written (or
declared) but never read anywhere in the application: `referral.
sla_profile_id` (always NULL — push.py/seed.py insert NULL into it; the
sweep looks up a referral's SLA window by joining sla_profile on
`state`/`active`, never by this FK) and `escalation.escalated_to_user_id`
(never written at all — only `sla_profile.escalate_to_role`, a role not a
specific user, is ever used). Both confirmed dead by grep across the
whole `server/` tree before this migration was written.

Also adds `uq_sla_profile_active_state`, a partial unique index on
`sla_profile(state) WHERE active` — nothing in the current seed data or
any experiment cohort violates it (checked before writing this), so this
is a pure safety net: without it, nothing stops two active profiles from
sharing a state, which would make app/domain/escalation.py's
`_BREACH_QUERY` return the same referral twice in one sweep pass. I5's
own partial index (`uq_escalation_open`) already prevents that from
becoming a double-escalation *event*, so this is defense in depth, not a
fix for an observed failure.

All data in this project is synthetic (frozen scope, CLAUDE.md) and both
dropped columns have only ever held NULL, so downgrade recreates them
empty rather than attempting any data restoration — same reasoning
migration 0004's own docstring gives for its own irreversible step.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("fk_referral_sla_profile", "referral", type_="foreignkey")
    op.drop_column("referral", "sla_profile_id")

    op.drop_constraint("fk_escalation_escalated_to_user", "escalation", type_="foreignkey")
    op.drop_column("escalation", "escalated_to_user_id")

    op.create_index(
        "uq_sla_profile_active_state",
        "sla_profile",
        ["state"],
        unique=True,
        postgresql_where=sa.text("active"),
    )


def downgrade() -> None:
    op.drop_index("uq_sla_profile_active_state", table_name="sla_profile")

    op.add_column(
        "escalation",
        sa.Column("escalated_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_escalation_escalated_to_user",
        "escalation",
        "app_user",
        ["escalated_to_user_id"],
        ["id"],
    )

    op.add_column(
        "referral", sa.Column("sla_profile_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_referral_sla_profile", "referral", "sla_profile", ["sla_profile_id"], ["id"]
    )
