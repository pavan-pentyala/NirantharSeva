"""patient age/sex, app_user display_name — Phase 4.1

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-20

D13/ADR-009: create_referral can now describe a brand-new patient inline
(name, age, sex, phone) instead of only naming one that already exists.
D15: app_user gets a display_name separate from its login handle.

All three columns are nullable. patient.age/sex are null for every patient
row written before this migration — no fake data backfilled for them (see
ADR-009's "consequences" section). app_user.display_name is nullable at the
schema level but app/seed.py fills it for every seeded user immediately
after this migration runs, so no shipped fixture is ever null in practice.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("patient", sa.Column("age", sa.Integer, nullable=True))
    op.add_column("patient", sa.Column("sex", sa.Text, nullable=True))
    op.add_column("app_user", sa.Column("display_name", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("app_user", "display_name")
    op.drop_column("patient", "sex")
    op.drop_column("patient", "age")
