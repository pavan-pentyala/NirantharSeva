"""referral domain — Phase 2.1

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-17

The real schema: referral state machine, org tree, users, patients, the
conflict record, and the escalation table (unwritten until Phase 5, but
created now so uq_escalation_open exists before anything could violate it —
see plan §6.1 and I5).

Two things worth reading before touching this file again:

1. **No DEFAULT now() on any timestamp.** Same rule as 0002 — every
   timestamp is written by the application from the injected Clock
   (docs/decisions/ADR-001.md), never by Postgres.

2. **event_seq is a shared sequence, not owned by either table.**
   docs/decisions/ADR-004.md: referral_event and toy_event both draw their
   `seq` from this one sequence so a single /sync/pull cursor can span both
   without gaps. It is deliberately NOT bound with `OWNED BY` to either
   table/column — an owned sequence is dropped automatically when its
   owning column is dropped, and toy_event is dropped at Phase 4 (D1 in
   docs/PHASE2_PLAN.md) while this sequence and referral_event must
   survive that drop.

Foreign keys are declared only where the phase plan names them explicitly
(referral.patient_id, referral_event.referral_id, app_user.org_unit_id) or
are the same single-parent shape (patient_alias.patient_id,
escalation.referral_id). The org/user cross-reference columns
(origin_user_id, origin_org_id, target_org_id, actor_user_id, and similar)
are left as bare UUID with no FK for this phase — Phase 2.2 is what
populates app_user and org_unit with real rows via real auth; constraining
them now would demand seed data that does not exist until then. See
docs/decisions/ADR-003.md and the P2.1 session report for the full
reasoning.

referral_event and sync_conflict both carry a `run_id` column though the
plan's raw SQL for Phase 2 does not list one — handoff §R8 requires
instrumentation on anything that handles a request or an op, matching the
run_id column toy_event already has. Cache/lookup tables (referral,
patient, escalation as given) do not get one; only the two tables that
record something happening during a specific run do.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REFERRAL_STATES = (
    "CREATED",
    "IN_TRANSIT",
    "ARRIVED",
    "TREATED",
    "BACK_REFERRED",
    "CLOSED",
    "ESCALATED",
    "LOST",
)
USER_ROLES = ("ASHA", "ANM", "MO", "SUPERVISOR", "SYSTEM")


def upgrade() -> None:
    referral_states_sql = ", ".join(f"'{s}'" for s in REFERRAL_STATES)
    user_roles_sql = ", ".join(f"'{r}'" for r in USER_ROLES)
    op.execute(f"CREATE TYPE referral_state AS ENUM ({referral_states_sql})")
    op.execute(f"CREATE TYPE user_role AS ENUM ({user_roles_sql})")

    referral_state = postgresql.ENUM(*REFERRAL_STATES, name="referral_state", create_type=False)
    user_role = postgresql.ENUM(*USER_ROLES, name="user_role", create_type=False)

    # D3/ADR-004: one sequence behind both event tables. setval's `value`
    # must be >= 1 (Postgres sequences MINVALUE 1 by default) — on an empty
    # toy_event, MAX(seq) is NULL and COALESCE(..., 0) alone is out of
    # range. The third setval argument (is_called) resolves both cases
    # without wasting a value: with existing rows, value=MAX(seq) and
    # is_called=true so the next nextval() returns MAX(seq)+1; on an empty
    # table, value=1 and is_called=false so the next nextval() returns 1
    # exactly, matching a freshly created sequence's own starting point.
    op.execute("CREATE SEQUENCE event_seq")
    op.execute(
        """SELECT setval(
             'event_seq',
             GREATEST(1, COALESCE((SELECT MAX(seq) FROM toy_event), 0)),
             (SELECT MAX(seq) FROM toy_event) IS NOT NULL
           )"""
    )
    op.execute("ALTER TABLE toy_event ALTER COLUMN seq SET DEFAULT nextval('event_seq')")

    op.create_table(
        "org_unit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column(
            "parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("org_unit.id"), nullable=True
        ),
    )

    op.create_table(
        "app_user",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column(
            "org_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_unit.id"),
            nullable=True,
        ),
        sa.Column("password_hash", sa.Text, nullable=False),
    )

    op.create_table(
        "patient",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("normalized_name", sa.Text, nullable=False),
        sa.Column("phone", sa.Text, nullable=True),
        sa.Column("village_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_table(
        "patient_alias",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id"),
            nullable=False,
        ),
        sa.Column("raw_name", sa.Text, nullable=False),
        sa.Column("match_method", sa.Text, nullable=True),
        sa.Column("match_score", sa.Numeric, nullable=True),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_table(
        "sla_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("state", referral_state, nullable=False),
        sa.Column("max_hours", sa.Integer, nullable=False),
        sa.Column("escalate_to_role", user_role, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "referral",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient.id"),
            nullable=False,
        ),
        sa.Column("origin_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("priority", sa.Text, nullable=True),
        sa.Column("current_state", referral_state, nullable=False),  # cache — I3
        sa.Column("state_entered_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("sla_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_device_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_server_time", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_table(
        "referral_event",
        sa.Column(
            "seq",
            sa.BigInteger,
            primary_key=True,
            autoincrement=False,
            server_default=sa.text("nextval('event_seq')"),
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "referral_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referral.id"),
            nullable=False,
        ),
        sa.Column("from_state", referral_state, nullable=True),  # null only on create
        sa.Column("to_state", referral_state, nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
            nullable=True,
        ),
        sa.Column("actor_role", user_role, nullable=False),  # D2 — never null
        sa.Column("device_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("server_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("lamport", sa.BigInteger, nullable=False),
        sa.Column("op_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("run_id", sa.Text, nullable=True),  # R8 — see module docstring
    )
    op.create_index("idx_event_referral", "referral_event", ["referral_id", "seq"])

    op.create_table(
        "escalation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "referral_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referral.id"),
            nullable=False,
        ),
        sa.Column("breached_state", referral_state, nullable=False),
        sa.Column("triggered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("escalated_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sla_profile_version", sa.Integer, nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # I5: double escalation is structurally impossible, not merely avoided.
    op.create_index(
        "uq_escalation_open",
        "escalation",
        ["referral_id", "breached_state"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )

    op.create_table(
        "sync_conflict",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field", sa.Text, nullable=True),
        sa.Column("winning_op_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("losing_op_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("detected_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("run_id", sa.Text, nullable=True),  # R8 — see module docstring
    )

    op.create_index(
        "idx_referral_open",
        "referral",
        ["current_state", "state_entered_at"],
        postgresql_where=sa.text("current_state NOT IN ('CLOSED','LOST')"),
    )
    op.create_index("idx_patient_norm", "patient", ["village_org_id", "normalized_name"])


def downgrade() -> None:
    op.drop_index("idx_patient_norm", table_name="patient")
    op.drop_index("idx_referral_open", table_name="referral")
    op.drop_table("sync_conflict")
    op.drop_index("uq_escalation_open", table_name="escalation")
    op.drop_table("escalation")
    op.drop_index("idx_event_referral", table_name="referral_event")
    op.drop_table("referral_event")
    op.drop_table("referral")
    op.drop_table("sla_profile")
    op.drop_table("patient_alias")
    op.drop_table("patient")
    op.drop_table("app_user")
    op.drop_table("org_unit")

    op.execute("ALTER TABLE toy_event ALTER COLUMN seq SET DEFAULT nextval('toy_event_seq_seq')")
    op.execute("DROP SEQUENCE event_seq")
    op.execute("DROP TYPE user_role")
    op.execute("DROP TYPE referral_state")
