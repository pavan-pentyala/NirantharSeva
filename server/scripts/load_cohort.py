"""Replays a generated cohort through the real API. docs/decisions/ADR-015.md.

The district (org_unit, app_user) is created by direct SQL — the same
pattern app/seed.py uses; there is no API for creating either (D29,
docs/PHASE7_PLAN.md). Referrals and their events go through the real
POST /sync/push, one authenticated session per generated user — exactly
the path a real device takes (ADR-006: origin_user_id/origin_org_id come
from whoever is logged in, never from the payload; ADR-009: the patient
is resolved by the same fuzzy pipeline every referral goes through).

Lives in scripts/, not generator/, because it needs an HTTP client and
httpx is a dev-group dependency (server/pyproject.toml) — same reasoning
as scripts/demo_walk.py. `client` is an injectable parameter so
tests/integration/test_load_cohort.py can hand it an ASGI-transport
client instead of a live socket, without this module knowing the
difference; the CLI entry point below builds a real one against
DEMO_API_URL.

Re-runnable against a partially loaded cohort nearly for free: every op_id
is uuid5-derived from the cohort's own referral_id and step, so a second
run finds every receipt already claimed (I1) and applies nothing new —
ADR-015's own "second cost" names this as the reason it is safe to build
the loader this way rather than needing its own resume bookkeeping.

`upto_device_time` exists for Phase 8's SimulatedClock runner, not for
P7.1 itself (P7.1 always calls with the default, None, meaning "push
everything"). A referral whose created_device_time is after the cutoff is
skipped whole, including all its events; a referral that is pushed but
whose events run past the cutoff has its later events skipped, in device
time order — a transition cannot apply out of order, so nothing after the
first skipped event for a referral is pushed either.
"""

import argparse
import asyncio
import csv
import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import async_session_factory

DEMO_API_URL = os.environ.get("DEMO_API_URL", "http://api:8000")
DEV_PASSWORD = "dev"  # app/seed.py's own constant — never a second one

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "nirantharseva.load_cohort")
_hasher = PasswordHasher()


def _op_id(key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, key)


@dataclass
class LoadReport:
    org_units_created: int = 0
    users_created: int = 0
    referrals_pushed: int = 0
    referrals_skipped: int = 0
    transitions_pushed: int = 0
    transitions_skipped: int = 0
    non_accepted: list[dict] = field(default_factory=list)
    elapsed_seconds: float = 0.0


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def _create_district(
    session_factory: async_sessionmaker[AsyncSession],
    org_rows: list[dict],
    user_rows: list[dict],
) -> None:
    """district.csv is written parent-first by generator/cohort.py
    (facilities, then sub-centres, then villages), so inserting in file
    order satisfies org_unit.parent_id's foreign key without a second
    pass. ON CONFLICT DO UPDATE, same as app/seed.py — idempotent, so a
    re-run over an already-loaded cohort just confirms the rows agree."""
    async with session_factory() as s, s.begin():
        for row in org_rows:
            await s.execute(
                text(
                    """INSERT INTO org_unit (id, name, type, parent_id)
                       VALUES (:id, :name, :type, :parent_id)
                       ON CONFLICT (id) DO UPDATE
                         SET name = EXCLUDED.name, type = EXCLUDED.type,
                             parent_id = EXCLUDED.parent_id"""
                ),
                {
                    "id": row["org_id"],
                    "name": row["name"],
                    "type": row["type"],
                    "parent_id": row["parent_id"] or None,
                },
            )
        for row in user_rows:
            await s.execute(
                text(
                    """INSERT INTO app_user (id, name, role, org_unit_id, password_hash)
                       VALUES (:id, :name, :role, :org_unit_id, :password_hash)
                       ON CONFLICT (name) DO UPDATE
                         SET role = EXCLUDED.role, org_unit_id = EXCLUDED.org_unit_id"""
                ),
                {
                    "id": row["user_id"],
                    "name": row["name"],
                    "role": row["role"],
                    "org_unit_id": row["org_id"],
                    "password_hash": _hasher.hash(DEV_PASSWORD),
                },
            )


async def _login(client: httpx.AsyncClient, username: str) -> dict:
    resp = await client.post("/auth/login", json={"username": username, "password": DEV_PASSWORD})
    resp.raise_for_status()
    return {"authorization": f"Bearer {resp.json()['access_token']}"}


async def _push_one(
    client: httpx.AsyncClient, headers: dict, device_id: str, op: dict, report: LoadReport
) -> str:
    resp = await client.post(
        "/sync/push", json={"device_id": device_id, "ops": [op]}, headers=headers
    )
    resp.raise_for_status()
    result = resp.json()["results"][0]
    if result["status"] != "accepted":
        report.non_accepted.append(
            {"op_id": op["op_id"], "operation": op["operation"], "status": result["status"]}
        )
    return result["status"]


def _create_op(referral_id: str, patient: dict, referral: dict) -> dict:
    return {
        "op_id": str(_op_id(f"referral:{referral_id}:create")),
        "entity": "referral",
        "entity_id": referral_id,
        "operation": "create_referral",
        "payload": {
            "patient_name": patient["name"],
            "age": int(patient["age"]),
            "sex": patient["sex"],
            "phone": patient["phone"] or None,
            "reason": referral["reason"],
            "priority": referral["priority"],
            "target_org_id": referral["target_org"],
        },
        "lamport": 1,
        "device_time": referral["created_device_time"],
    }


def _transition_op(referral_id: str, event: dict) -> dict:
    return {
        "op_id": str(_op_id(f"referral:{referral_id}:event:{event['step']}")),
        "entity": "referral",
        "entity_id": referral_id,
        "operation": "transition",
        "payload": {"from_state": event["from_state"], "to_state": event["to_state"]},
        "lamport": int(event["step"]) + 1,
        "device_time": event["device_time"],
    }


async def load(
    cohort_dir: Path,
    upto_device_time: datetime | None = None,
    *,
    client: httpx.AsyncClient | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> LoadReport:
    session_factory = session_factory or async_session_factory
    owns_client = client is None
    client = client or httpx.AsyncClient(base_url=DEMO_API_URL, timeout=30.0)

    started = time.monotonic()
    report = LoadReport()

    try:
        org_rows = _read_csv(cohort_dir / "district.csv")
        user_rows = _read_csv(cohort_dir / "users.csv")
        patient_rows = _read_csv(cohort_dir / "patients.csv")
        referral_rows = _read_csv(cohort_dir / "referrals.csv")
        event_rows = _read_csv(cohort_dir / "events.csv")

        await _create_district(session_factory, org_rows, user_rows)
        report.org_units_created = len(org_rows)
        report.users_created = len(user_rows)

        patients_by_id = {p["record_id"]: p for p in patient_rows}
        events_by_referral: dict[str, list[dict]] = defaultdict(list)
        for e in event_rows:
            events_by_referral[e["referral_id"]].append(e)
        for rows in events_by_referral.values():
            rows.sort(key=lambda e: int(e["step"]))

        user_org_role: dict[tuple[str, str], str] = {
            (u["org_id"], u["role"]): u["name"] for u in user_rows
        }

        tokens: dict[str, dict] = {}

        async def token_for(username: str) -> dict:
            if username not in tokens:
                tokens[username] = await _login(client, username)
            return tokens[username]

        for referral in referral_rows:
            referral_id = referral["referral_id"]
            created_at = datetime.fromisoformat(referral["created_device_time"])
            if upto_device_time is not None and created_at > upto_device_time:
                report.referrals_skipped += 1
                report.transitions_skipped += len(events_by_referral.get(referral_id, []))
                continue

            patient = patients_by_id[referral["patient_record_id"]]
            headers = await token_for(referral["origin_user"])
            op = _create_op(referral_id, patient, referral)
            await _push_one(client, headers, f"cohort-{referral['origin_user']}", op, report)
            report.referrals_pushed += 1

            for event in events_by_referral.get(referral_id, []):
                event_time = datetime.fromisoformat(event["device_time"])
                if upto_device_time is not None and event_time > upto_device_time:
                    remaining = len(events_by_referral[referral_id]) - int(event["step"]) + 1
                    report.transitions_skipped += remaining
                    break

                if event["actor_role"] == "ASHA":
                    actor = referral["origin_user"]
                else:  # MO — the target facility's own MO (GUARDS[ARRIVED/TREATED/BACK_REFERRED])
                    actor = user_org_role[(referral["target_org"], "MO")]
                headers = await token_for(actor)
                op = _transition_op(referral_id, event)
                await _push_one(client, headers, f"cohort-{actor}", op, report)
                report.transitions_pushed += 1
    finally:
        if owns_client:
            await client.aclose()

    report.elapsed_seconds = time.monotonic() - started
    return report


def _print_report(report: LoadReport) -> None:
    print(
        f"orgs={report.org_units_created} users={report.users_created} "
        f"referrals={report.referrals_pushed} (+{report.referrals_skipped} skipped) "
        f"transitions={report.transitions_pushed} (+{report.transitions_skipped} skipped) "
        f"non_accepted={len(report.non_accepted)} "
        f"elapsed={report.elapsed_seconds:.1f}s"
    )
    for row in report.non_accepted[:20]:
        print(f"  non-accepted: {row}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(load(args.cohort))
    _print_report(report)


if __name__ == "__main__":
    main()
