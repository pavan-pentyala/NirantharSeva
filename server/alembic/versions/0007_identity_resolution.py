"""identity resolution — merged patients, normalized aliases, the review
queue — Phase 6, P6.2

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-21

docs/PHASE6_PLAN.md's "Contracts fixed now" section is the source of truth
for this schema; §10.1/§10.2 of docs/IMPLEMENTATION_PLAN.md, ADR-013 and
ADR-014 are the why.

Three changes:

1. `patient.merged_into_id` — self-referential, nullable. Set by
   `POST /identity/reviews/{id}/decide`'s merge outcome
   (app/api/identity.py); never by anything else. A merged-away row is
   recoverable in SQL but has no UI path back (plan's "Not in this plan").

2. `patient_alias.normalized_alias` — NOT NULL, no server_default and no
   backfill needed: the table is empty (verified — P6.1's gold set writes
   directly to `patient`, never to `patient_alias`, and nothing before
   this migration ever wrote an alias row either). Re-verify before running
   this against any database that is not freshly seeded.

3. `identity_review` — the queue itself, plus `uq_identity_review_open`,
   a partial unique index on (new_patient_id, candidate_patient_id) WHERE
   status='pending'. Same shape as migration 0003's `uq_escalation_open`:
   the duplicate-queue guard is structural, not a Python `if`. No
   `DEFAULT now()` on any timestamp (migration 0003's rule, still in
   force) — `created_at`/`decided_at` are always written by the caller
   with the injected Clock.

Also backfills `patient.normalized_name` for every pre-existing row: those
were written by ADR-009's `name.strip().lower()`, not P6.1's
`app.linkage.normalize.normalize` (NFKD + diacritic strip + whitespace
collapse) — without this, the exact-match step in
`app/linkage/pipeline.py` silently misses every patient created before
Phase 6 (docs/PHASE6_PLAN.md "Traps"). Row-by-row in Python, not a SQL
expression, because NFKD decomposition has no simple SQL equivalent and
the fixture-scale patient table makes per-row UPDATEs cheap enough that
inventing one is not worth it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.linkage.normalize import normalize

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patient", sa.Column("merged_into_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_patient_merged_into", "patient", "patient", ["merged_into_id"], ["id"]
    )

    op.add_column("patient_alias", sa.Column("normalized_alias", sa.Text, nullable=False))

    op.create_table(
        "identity_review",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "new_patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id"),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id"), nullable=True
        ),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("run_id", sa.Text, nullable=True),  # R8
    )
    # I5's sibling for identity: double-queueing the same pending pair is
    # structurally impossible, not merely avoided. See app/sync/push.py's
    # ON CONFLICT (new_patient_id, candidate_patient_id) WHERE status =
    # 'pending' DO NOTHING RETURNING id — naming the predicate explicitly
    # is required, or the insert raises instead of no-op'ing (P5.1's trap).
    op.create_index(
        "uq_identity_review_open",
        "identity_review",
        ["new_patient_id", "candidate_patient_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, name FROM patient")).all()
    for row in rows:
        connection.execute(
            sa.text("UPDATE patient SET normalized_name = :n WHERE id = :id"),
            {"n": normalize(row.name), "id": row.id},
        )


def downgrade() -> None:
    op.drop_index("uq_identity_review_open", table_name="identity_review")
    op.drop_table("identity_review")
    op.drop_column("patient_alias", "normalized_alias")
    op.drop_constraint("fk_patient_merged_into", "patient", type_="foreignkey")
    op.drop_column("patient", "merged_into_id")
