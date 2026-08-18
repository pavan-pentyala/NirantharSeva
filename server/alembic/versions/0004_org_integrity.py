"""org integrity — Phase 2.2

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-18

D8 (docs/PHASE2_PLAN.md): the seed script now gives the org/user
cross-reference columns something real to point at, so this migration adds
the FKs P2.1 deliberately left bare, plus the constraint that turns the
data-leak test in P2.2 from a vacuous pass into a real one.

**Not backward-compatible with rows written during P2.1.** Every referral
written before this migration has origin_org_id IS NULL, and NULL IN
(subtree) is never true, so `origin_org_id SET NOT NULL` cannot apply to a
database holding those rows. This pre-checks for NULLs and raises with a
message naming the fix, rather than letting Postgres emit a bare
NotNullViolation. All data in this project is synthetic by explicit choice
(CLAUDE.md, frozen scope), so `docker compose down -v` costs nothing real.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    null_count = conn.execute(
        sa.text("SELECT count(*) FROM referral WHERE origin_org_id IS NULL")
    ).scalar_one()
    if null_count:
        raise RuntimeError(
            f"{null_count} referral row(s) have origin_org_id IS NULL — these were "
            "written before Phase 2.2's real auth existed to populate it (see D8, "
            "docs/PHASE2_PLAN.md). This migration cannot apply on top of them. "
            "Run `docker compose down -v` to wipe the (synthetic) data and start "
            "from a clean database, then re-run migrations and the seed."
        )

    op.create_unique_constraint("uq_app_user_name", "app_user", ["name"])
    op.create_index("idx_referral_origin_org", "referral", ["origin_org_id"])

    op.create_foreign_key(
        "fk_referral_origin_org", "referral", "org_unit", ["origin_org_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_referral_target_org", "referral", "org_unit", ["target_org_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_patient_village_org", "patient", "org_unit", ["village_org_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_referral_origin_user", "referral", "app_user", ["origin_user_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_referral_event_actor_user",
        "referral_event",
        "app_user",
        ["actor_user_id"],
        ["id"],
    )
    op.create_foreign_key("fk_patient_created_by", "patient", "app_user", ["created_by"], ["id"])
    op.create_foreign_key(
        "fk_patient_alias_confirmed_by",
        "patient_alias",
        "app_user",
        ["confirmed_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_escalation_escalated_to_user",
        "escalation",
        "app_user",
        ["escalated_to_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_sync_conflict_resolved_by",
        "sync_conflict",
        "app_user",
        ["resolved_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_referral_sla_profile", "referral", "sla_profile", ["sla_profile_id"], ["id"]
    )

    op.alter_column("referral", "origin_org_id", nullable=False)


def downgrade() -> None:
    op.alter_column("referral", "origin_org_id", nullable=True)

    op.drop_constraint("fk_referral_sla_profile", "referral", type_="foreignkey")
    op.drop_constraint("fk_sync_conflict_resolved_by", "sync_conflict", type_="foreignkey")
    op.drop_constraint("fk_escalation_escalated_to_user", "escalation", type_="foreignkey")
    op.drop_constraint("fk_patient_alias_confirmed_by", "patient_alias", type_="foreignkey")
    op.drop_constraint("fk_patient_created_by", "patient", type_="foreignkey")
    op.drop_constraint("fk_referral_event_actor_user", "referral_event", type_="foreignkey")
    op.drop_constraint("fk_referral_origin_user", "referral", type_="foreignkey")
    op.drop_constraint("fk_patient_village_org", "patient", type_="foreignkey")
    op.drop_constraint("fk_referral_target_org", "referral", type_="foreignkey")
    op.drop_constraint("fk_referral_origin_org", "referral", type_="foreignkey")

    op.drop_index("idx_referral_origin_org", table_name="referral")
    op.drop_constraint("uq_app_user_name", "app_user", type_="unique")
