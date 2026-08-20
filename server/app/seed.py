"""D4's fixture (docs/PHASE2_PLAN.md) — a small hand-written district, just
big enough to prove org scoping. Replaced wholesale by the P7 cohort
generator.

    PHC Ramnagar            (mo1 . supervisor1)
     `-- Sub-centre Kotwali (anm1)
          |-- Village A     (asha_a)
          `-- Village B     (asha_b)

Idempotent: every row uses a deterministic id derived from a stable key
(org_unit/app_user names, patient names), so re-running never duplicates
data. org_unit and app_user rows are upserted (ON CONFLICT ... DO UPDATE) so
a changed role or org_unit_id in this file takes effect on the next seed
run. Patient and referral rows are ON CONFLICT DO NOTHING — fixture data,
not meant to drift once written.

Every referral gets its CREATED event appended in the same statement group
as the referral row (I3 — the event log is the truth, never just the
cache). Uses the injected Clock — see docs/decisions/ADR-001.md, which
applies to this file too, and which CI enforces with a grep.

Invoked as `python -m app.seed`. Also called by
server/tests/conftest.py's session-scoped seed fixture, so demo data and
test data never drift apart.
"""

import asyncio
import json
import uuid
from typing import Any

from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock, get_clock
from app.config import get_settings
from app.db import async_session_factory
from app.domain.states import Role, State

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "nirantharseva.seed")
_hasher = PasswordHasher()


def _stable_id(key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, key)


ORG_UNITS = [
    {"key": "org:PHC Ramnagar", "name": "PHC Ramnagar", "type": "PHC", "parent": None},
    {
        "key": "org:Sub-centre Kotwali",
        "name": "Sub-centre Kotwali",
        "type": "SUB_CENTRE",
        "parent": "org:PHC Ramnagar",
    },
    {
        "key": "org:Village A",
        "name": "Village A",
        "type": "VILLAGE",
        "parent": "org:Sub-centre Kotwali",
    },
    {
        "key": "org:Village B",
        "name": "Village B",
        "type": "VILLAGE",
        "parent": "org:Sub-centre Kotwali",
    },
]

USERS = [
    {"name": "asha_a", "role": Role.ASHA, "org": "org:Village A", "display_name": "Sunita Kumari"},
    {"name": "asha_b", "role": Role.ASHA, "org": "org:Village B", "display_name": "Meena Devi"},
    {
        "name": "anm1",
        "role": Role.ANM,
        "org": "org:Sub-centre Kotwali",
        "display_name": "Radha Singh",
    },
    {
        "name": "mo1",
        "role": Role.MO,
        "org": "org:PHC Ramnagar",
        "display_name": "Dr. Arvind Sharma",
    },
    {
        "name": "supervisor1",
        "role": Role.SUPERVISOR,
        "org": "org:PHC Ramnagar",
        "display_name": "Vikram Rathore",
    },
]
DEV_PASSWORD = "dev"

PATIENTS = [
    {
        "key": "patient:Lakshmi Devi",
        "name": "Lakshmi Devi",
        "phone": "9800000001",
        "org": "org:Village A",
        "age": 45,
        "sex": "F",
    },
    {
        "key": "patient:Ramesh Kumar",
        "name": "Ramesh Kumar",
        "phone": "9800000002",
        "org": "org:Village A",
        "age": 62,
        "sex": "M",
    },
    {
        "key": "patient:Fatima Begum",
        "name": "Fatima Begum",
        "phone": "9800000003",
        "org": "org:Village B",
        "age": 38,
        "sex": "F",
    },
    {
        "key": "patient:Suresh Yadav",
        "name": "Suresh Yadav",
        "phone": "9800000004",
        "org": "org:Village B",
        "age": 50,
        "sex": "M",
    },
]

# One referral per village (D4). target_org_id is always an ancestor of
# origin_org_id — the property ADR-005's origin-only filtering relies on,
# machine-checked by a test.
REFERRALS = [
    {
        "key": "referral:Village A",
        "patient": "patient:Lakshmi Devi",
        "origin_org": "org:Village A",
        "origin_user": "asha_a",
        "target_org": "org:PHC Ramnagar",
        "reason": "fever, referred for evaluation",
        "priority": "normal",
    },
    {
        "key": "referral:Village B",
        "patient": "patient:Fatima Begum",
        "origin_org": "org:Village B",
        "origin_user": "asha_b",
        "target_org": "org:PHC Ramnagar",
        "reason": "fever, referred for evaluation",
        "priority": "normal",
    },
]


async def seed(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    clock: Clock | None = None,
) -> None:
    session_factory = session_factory or async_session_factory
    clock = clock or get_clock()
    settings = get_settings()

    org_ids: dict[str, uuid.UUID] = {row["key"]: _stable_id(row["key"]) for row in ORG_UNITS}
    user_ids: dict[str, uuid.UUID] = {}

    async with session_factory() as s, s.begin():
        for row in ORG_UNITS:
            parent_id = org_ids[row["parent"]] if row["parent"] else None
            await s.execute(
                text(
                    """INSERT INTO org_unit (id, name, type, parent_id)
                       VALUES (:id, :name, :type, :parent_id)
                       ON CONFLICT (id) DO UPDATE
                         SET name = EXCLUDED.name, type = EXCLUDED.type,
                             parent_id = EXCLUDED.parent_id"""
                ),
                {
                    "id": org_ids[row["key"]],
                    "name": row["name"],
                    "type": row["type"],
                    "parent_id": parent_id,
                },
            )

        for user in USERS:
            user_id = _stable_id(f"user:{user['name']}")
            password_hash = _hasher.hash(DEV_PASSWORD)
            result = await s.execute(
                text(
                    """INSERT INTO app_user
                         (id, name, role, org_unit_id, password_hash, display_name)
                       VALUES (:id, :name, :role, :org_unit_id, :password_hash, :display_name)
                       ON CONFLICT (name) DO UPDATE
                         SET role = EXCLUDED.role, org_unit_id = EXCLUDED.org_unit_id,
                             display_name = EXCLUDED.display_name
                       RETURNING id"""
                ),
                {
                    "id": user_id,
                    "name": user["name"],
                    "role": user["role"].value,
                    "org_unit_id": org_ids[user["org"]],
                    "password_hash": password_hash,
                    "display_name": user["display_name"],
                },
            )
            user_ids[user["name"]] = result.scalar_one()

        patient_ids: dict[str, uuid.UUID] = {}
        now = clock.now()
        for patient in PATIENTS:
            patient_id = _stable_id(patient["key"])
            patient_ids[patient["key"]] = patient_id
            await s.execute(
                text(
                    """INSERT INTO patient
                         (id, name, normalized_name, phone, village_org_id, age, sex, created_at)
                       VALUES
                         (:id, :name, :normalized_name, :phone, :village_org_id, :age, :sex,
                          :created_at)
                       ON CONFLICT (id) DO NOTHING"""
                ),
                {
                    "id": patient_id,
                    "name": patient["name"],
                    "normalized_name": patient["name"].lower(),
                    "phone": patient["phone"],
                    "village_org_id": org_ids[patient["org"]],
                    "age": patient["age"],
                    "sex": patient["sex"],
                    "created_at": now,
                },
            )

        for referral in REFERRALS:
            referral_id = _stable_id(referral["key"])
            origin_user_id = user_ids[referral["origin_user"]]
            payload: dict[str, Any] = {
                "reason": referral["reason"],
                "priority": referral["priority"],
            }
            await s.execute(
                text(
                    """INSERT INTO referral
                         (id, patient_id, origin_user_id, origin_org_id, target_org_id,
                          reason, priority, current_state, state_entered_at,
                          sla_profile_id, created_device_time, created_server_time)
                       VALUES
                         (:id, :patient_id, :origin_user_id, :origin_org_id, :target_org_id,
                          :reason, :priority, :state, :now,
                          NULL, :now, :now)
                       ON CONFLICT (id) DO NOTHING"""
                ),
                {
                    "id": referral_id,
                    "patient_id": patient_ids[referral["patient"]],
                    "origin_user_id": origin_user_id,
                    "origin_org_id": org_ids[referral["origin_org"]],
                    "target_org_id": org_ids[referral["target_org"]],
                    "reason": referral["reason"],
                    "priority": referral["priority"],
                    "state": State.CREATED.value,
                    "now": now,
                },
            )
            await s.execute(
                text(
                    """INSERT INTO referral_event
                         (id, referral_id, from_state, to_state, actor_user_id, actor_role,
                          device_time, server_time, lamport, op_id, device_id, payload, run_id)
                       VALUES
                         (:id, :referral_id, NULL, :to_state, :actor_user_id, :actor_role,
                          :now, :now, 1, :op_id, 'seed', CAST(:payload AS jsonb), :run_id)
                       ON CONFLICT (op_id) DO NOTHING"""
                ),
                {
                    "id": uuid.uuid4(),
                    "referral_id": referral_id,
                    "to_state": State.CREATED.value,
                    "actor_user_id": origin_user_id,
                    "actor_role": Role.ASHA.value,
                    "now": now,
                    "op_id": _stable_id(f"{referral['key']}:create_event"),
                    "payload": json.dumps(payload),
                    "run_id": settings.run_id,
                },
            )


if __name__ == "__main__":
    asyncio.run(seed())
    print("Seeded PHC Ramnagar district: 4 org units, 5 users, 4 patients, 2 referrals.")
