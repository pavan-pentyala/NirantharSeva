"""app_user.phone — Phase 7, P7.3 B3

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-23

docs/PHASE7_PLAN.md's P7.3 backlog, item B3. The supervisor dashboard needs
a number to call about an overdue referral, and it needs to be the *ASHA's*
number, not the patient's — patient.phone is nullable by design (ADR-014)
and often absent, which is the entire premise of that ADR, so it cannot
stand in here.

Nullable, same reasoning as migration 0005's display_name: no fake data
backfilled for any pre-existing row. app/seed.py fills it for every seeded
user immediately after this migration runs, so no shipped fixture is ever
null in practice.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("phone", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("app_user", "phone")
