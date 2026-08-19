"""Demo walk: drives a referral CREATED -> ... -> CLOSED through the real
/sync/push, including a genuine two-device conflict and a stale write
through app/sync/conflicts.py. D12 (docs/PHASE3_PLAN.md) — not
hand-INSERTed rows.

Run as `docker compose run --rm api python scripts/demo_walk.py`. Lives in
scripts/, not app/, because it needs an HTTP client and httpx is a
dev-group dependency (server/pyproject.toml) — importing it from app/
would be bad layering, and promoting httpx to a runtime dependency is an
ask-the-user change this phase does not make.

Idempotent by I1, not a guard: every op_id and the referral's entity_id
are uuid5-derived from a stable key, the same pattern app/seed.py's
_stable_id uses. A second run finds every receipt already claimed and
applies nothing — the second run is itself a proof of I1, not just a
convenience.

`docker compose run --rm api ...` starts a *new* container on the compose
network — localhost is not the API there. DEMO_API_URL defaults to
http://api:8000; override it for a host run.
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime

import httpx

from app.seed import _stable_id as _seed_stable_id
from app.seed import seed

DEMO_API_URL = os.environ.get("DEMO_API_URL", "http://api:8000")
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "nirantharseva.demo_walk")
DEVICE_TIME = datetime(2026, 8, 19, 9, 0, tzinfo=UTC).isoformat()


def _stable_id(key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, key)


# The demo owns its own referral — it must never advance a seeded one
# (docs/PHASE3_PLAN.md trap 8), since app/seed.py's ON CONFLICT DO NOTHING
# means a mutated seeded referral is never reset, which would poison
# tests/integration/test_org_scoping.py's assertions.
REFERRAL_ID = _stable_id("referral")
PATIENT_ID = _seed_stable_id("patient:Lakshmi Devi")  # seeded, Village A

# user, device, from_state, to_state, lamport, expected status.
# Step 3 is the other non-advancing row of the conflict table
# (accepted_stale); step 4 is a genuine conflict — the cache is already
# IN_TRANSIT (from step 2) so from_state != current_state, and 20 > 11
# sends decide() to "conflict" rather than "accepted_stale". anm1 is used
# there because ANM is in GUARDS[IN_TRANSIT] and Sub-centre Kotwali is an
# ancestor of Village A, so the write-path org-scope check passes.
STEPS = [
    ("asha_a", "demo-phone-a", None, "CREATED", 10, "accepted"),
    ("asha_a", "demo-phone-a", "CREATED", "IN_TRANSIT", 11, "accepted"),
    ("asha_a", "demo-phone-c", "CREATED", "IN_TRANSIT", 5, "accepted_stale"),
    ("anm1", "demo-phone-b", "CREATED", "IN_TRANSIT", 20, "conflict"),
    ("mo1", "demo-phone-d", "IN_TRANSIT", "ARRIVED", 30, "accepted"),
    ("mo1", "demo-phone-d", "ARRIVED", "TREATED", 31, "accepted"),
    ("mo1", "demo-phone-d", "TREATED", "BACK_REFERRED", 32, "accepted"),
    ("asha_a", "demo-phone-a", "BACK_REFERRED", "CLOSED", 33, "accepted"),
]


def _op(step_index: int, from_state: str | None, to_state: str, lamport: int) -> dict:
    op_id = _stable_id(f"step:{step_index}")
    if from_state is None:
        operation, payload = (
            "create_referral",
            {
                "patient_id": str(PATIENT_ID),
                "reason": "fever, referred for evaluation",
                "priority": "normal",
            },
        )
    else:
        operation, payload = "transition", {"from_state": from_state, "to_state": to_state}
    return {
        "op_id": str(op_id),
        "entity": "referral",
        "entity_id": str(REFERRAL_ID),
        "operation": operation,
        "payload": payload,
        "lamport": lamport,
        "device_time": DEVICE_TIME,
    }


def _login(client: httpx.Client, username: str) -> dict:
    resp = client.post(f"{DEMO_API_URL}/auth/login", json={"username": username, "password": "dev"})
    resp.raise_for_status()
    return {"authorization": f"Bearer {resp.json()['access_token']}"}


def run() -> None:
    asyncio.run(seed())
    print(f"Seeded. Demo referral id: {REFERRAL_ID}")

    with httpx.Client(timeout=10.0) as client:
        users = {user for user, *_ in STEPS}
        tokens = {user: _login(client, user) for user in users}

        for i, (user, device, frm, to, lamport, expected) in enumerate(STEPS, start=1):
            op = _op(i, frm, to, lamport)
            resp = client.post(
                f"{DEMO_API_URL}/sync/push",
                json={"device_id": device, "ops": [op]},
                headers=tokens[user],
            )
            resp.raise_for_status()
            result = resp.json()["results"][0]
            assert result["status"] == expected, (
                f"step {i} ({user}, {frm} -> {to}): expected {expected!r}, got {result!r}"
            )
            print(f"step {i}: {user} {frm} -> {to} (lamport {lamport}) -> {result['status']}")

    print()
    print("Walk complete. Verify and inspect with:")
    print("  docker compose run --rm api python -m app.verify_replay")
    print(
        f"  TOKEN=$(curl -s -X POST {DEMO_API_URL}/auth/login "
        "-H 'content-type: application/json' "
        '-d \'{"username":"asha_a","password":"dev"}\' | '
        "python3 -c \"import json,sys; print(json.load(sys.stdin)['access_token'])\")"
    )
    print(
        f"  curl -s {DEMO_API_URL}/referrals/{REFERRAL_ID}/timeline "
        '-H "authorization: Bearer $TOKEN" | python3 -m json.tool'
    )


if __name__ == "__main__":
    run()
