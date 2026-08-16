"""baseline — empty revision, Phase 0

Revision ID: 0001
Revises:
Create Date: 2026-08-16

Nothing to migrate yet. Phase 1's toy model is revision 0002, giving the
"never edit a shipped migration" rule a clean starting point.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
