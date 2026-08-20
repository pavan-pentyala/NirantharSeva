"""Concurrent appends produce no cursor gap.

Without acquire_seq_lock (docs/decisions/ADR-002.md), a transaction can be
allocated a lower seq than one that commits before it, so a client pulling
in between could permanently miss the lower-seq event once it advances its
cursor past the higher one. This fires N concurrent pushes through the real
ASGI app (real interleaving at await points, real Postgres) and checks the
pull afterwards sees every one of them, with a cursor that is exactly the
maximum seq seen — proof nothing was skipped.

Ported from the toy model to referral create_referral ops at Phase 4.3
(D1/D7 — the toy model was dropped). Each concurrent op creates an
independent new referral (distinct entity_id, distinct patient), so every
push is "accepted" — no conflicts to reason about here, this test is only
about seq/cursor ordering.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import async_session_factory

CONCURRENCY = 20


def _op(entity_id, patient_name):
    return {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "create_referral",
        "payload": {"patient_name": patient_name, "reason": "fever", "priority": "normal"},
        "lamport": 1,
        "device_time": datetime(2026, 8, 10, 9, 0, tzinfo=UTC).isoformat(),
    }


async def _push_one(client, headers, device_id, entity_id, patient_name):
    body = {"device_id": device_id, "ops": [_op(entity_id, patient_name)]}
    resp = await client.post("/sync/push", json=body, headers=headers)
    assert resp.status_code == 200
    return resp.json()["results"][0]


async def test_concurrent_pushes_leave_no_gap_in_the_pull_cursor(client, auth_headers):
    async with async_session_factory() as session:
        before = await session.execute(text("SELECT COALESCE(MAX(seq), 0) FROM referral_event"))
        cursor_before = before.scalar_one()

    entity_ids = [uuid.uuid4() for _ in range(CONCURRENCY)]
    push_results = await asyncio.gather(
        *[
            _push_one(client, auth_headers, f"d-{i}", entity_ids[i], f"Cursor Test Patient {i}")
            for i in range(CONCURRENCY)
        ]
    )
    assert all(r["status"] == "accepted" for r in push_results)
    pushed_seqs = sorted(r["server_seq"] for r in push_results)

    resp = await client.get(f"/sync/pull?since={cursor_before}&limit=1000", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    pulled_seqs = sorted(e["seq"] for e in body["events"])

    # Every seq the pushes were told about must show up in the pull — none
    # skipped, none swallowed by a concurrent commit racing ahead of it.
    assert set(pushed_seqs).issubset(set(pulled_seqs))
    # And the visible range has no holes: a contiguous run of integers.
    full_range = list(range(pulled_seqs[0], pulled_seqs[-1] + 1))
    assert pulled_seqs == full_range
    assert body["cursor"] == pulled_seqs[-1]
