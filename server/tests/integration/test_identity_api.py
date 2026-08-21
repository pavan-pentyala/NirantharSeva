"""GET /identity/reviews and POST /identity/reviews/{id}/decide.
docs/decisions/ADR-013.md, docs/PHASE6_PLAN.md P6.2 exit criteria.

Reuses the seeded org tree rather than inserting new org_unit rows —
tests/integration/test_org_units.py and tests/unit/test_scoping.py both
assert the *exact* set of seeded org names, so a throwaway org created
here would fail them, elsewhere, for a reason that has nothing to do with
what they test. PHC Ramnagar (the ANM's own org's *parent*, never a
descendant of it) stands in for "outside anm1's subtree" — subtree only
ever goes downward, so this needs no new fixture.

Village B carries every patient/referral this file inserts directly,
never Village A — Village A is where tests/integration/
test_push_identity_resolution.py and test_normalized_name_backfill.py run
real fuzzy scoring, and (per observation 44, docs/PHASE2_OBSERVATIONS.md)
token_set_ratio scores on shared words regardless of which test wrote
them. decide() and list_reviews() never call app/linkage/scoring.py, so
which village this file's bare-insert fixtures sit in doesn't matter to
them — but it matters to every OTHER file's fuzzy-scoring tests that share
a live, never-rolled-back database. The one test that pushes a real
create_referral op must use Village A for real, since app/sync/push.py
resolves village_org_id from the actor's own org — that one follows
observation 44's rule of a real, pre-verified score band instead.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import async_session_factory
from app.domain.states import Role, State
from app.linkage.blocking import block
from app.seed import _stable_id as _seed_stable_id
from app.sync.event_log import insert_referral_event

PHC_RAMNAGAR = _seed_stable_id("org:PHC Ramnagar")
VILLAGE_A = _seed_stable_id("org:Village A")
VILLAGE_B = _seed_stable_id("org:Village B")
_NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)


async def _insert_patient(name: str, village_org_id) -> uuid.UUID:
    patient_id = uuid.uuid4()
    async with async_session_factory() as s, s.begin():
        await s.execute(
            text(
                """INSERT INTO patient (id, name, normalized_name, village_org_id, created_at)
                   VALUES (:id, :name, :norm, :village_org_id, :now)"""
            ),
            {
                "id": patient_id,
                "name": name,
                "norm": name.strip().lower(),
                "village_org_id": village_org_id,
                "now": _NOW,
            },
        )
    return patient_id


async def _insert_pending_review(new_patient_id, candidate_patient_id, score=85.0) -> uuid.UUID:
    review_id = uuid.uuid4()
    async with async_session_factory() as s, s.begin():
        await s.execute(
            text(
                """INSERT INTO identity_review
                     (id, new_patient_id, candidate_patient_id, score, method, created_at)
                   VALUES
                     (:id, :new_patient_id, :candidate_patient_id, :score, 'review_queue', :now)"""
            ),
            {
                "id": review_id,
                "new_patient_id": new_patient_id,
                "candidate_patient_id": candidate_patient_id,
                "score": score,
                "now": _NOW,
            },
        )
    return review_id


async def _insert_referral(patient_id, village_org_id) -> uuid.UUID:
    """A referral row plus its CREATED event, in the same transaction —
    I3 (the event log is the truth), the same discipline app/seed.py's own
    REFERRALS loop follows. A referral with no backing event fails
    app/verify_replay.py for the whole database, not just this test."""
    referral_id = uuid.uuid4()
    async with async_session_factory() as s, s.begin():
        await s.execute(
            text(
                """INSERT INTO referral
                     (id, patient_id, origin_org_id, current_state, state_entered_at,
                      created_server_time)
                   VALUES (:id, :patient_id, :origin_org_id, 'CREATED', :now, :now)"""
            ),
            {
                "id": referral_id,
                "patient_id": patient_id,
                "origin_org_id": village_org_id,
                "now": _NOW,
            },
        )
        await insert_referral_event(
            s,
            referral_id=referral_id,
            from_state=None,
            to_state=State.CREATED.value,
            actor_user_id=None,
            actor_role=Role.SYSTEM.value,
            device_time=_NOW,
            server_time=_NOW,
            lamport=1,
            op_id=uuid.uuid4(),
            device_id="test-fixture",
            payload=None,
            run_id=None,
        )
    return referral_id


async def _aliases_for(patient_id) -> list:
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT raw_name, patient_id FROM patient_alias WHERE patient_id=:id"),
            {"id": patient_id},
        )
        return result.all()


async def test_anm_sees_only_pairs_within_her_subtree(client, anm_auth_headers):
    in_new = await _insert_patient("Scope InBranch New", VILLAGE_B)
    in_candidate = await _insert_patient("Scope InBranch Candidate", VILLAGE_B)
    in_review = await _insert_pending_review(in_new, in_candidate)

    # PHC Ramnagar is anm1's own org's PARENT — outside her subtree, which
    # only descends from Sub-centre Kotwali.
    out_new = await _insert_patient("Scope OutBranch New", PHC_RAMNAGAR)
    out_candidate = await _insert_patient("Scope OutBranch Candidate", PHC_RAMNAGAR)
    out_review = await _insert_pending_review(out_new, out_candidate)

    resp = await client.get("/identity/reviews", headers=anm_auth_headers)
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["reviews"]}
    assert str(in_review) in ids
    assert str(out_review) not in ids


async def test_decide_merge_repoints_referrals_writes_alias_marks_merged_and_is_idempotent(
    client, anm_auth_headers
):
    new_patient = await _insert_patient("Merge Test New Person", VILLAGE_B)
    candidate = await _insert_patient("Merge Test Candidate Person", VILLAGE_B)
    referral_id = await _insert_referral(new_patient, VILLAGE_B)
    review_id = await _insert_pending_review(new_patient, candidate)

    resp = await client.post(
        f"/identity/reviews/{review_id}/decide",
        json={"decision": "merge"},
        headers=anm_auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"id": str(review_id), "status": "merged"}

    async with async_session_factory() as session:
        referral_row = (
            await session.execute(
                text("SELECT patient_id FROM referral WHERE id=:id"), {"id": referral_id}
            )
        ).one()
        assert referral_row.patient_id == candidate

        patient_row = (
            await session.execute(
                text("SELECT merged_into_id FROM patient WHERE id=:id"), {"id": new_patient}
            )
        ).one()
        assert patient_row.merged_into_id == candidate

    aliases = await _aliases_for(candidate)
    assert len(aliases) == 1
    assert aliases[0].raw_name == "Merge Test New Person"

    # A second identical POST is harmless (ADR-013) — same outcome, no
    # second alias, referral not touched again.
    resp2 = await client.post(
        f"/identity/reviews/{review_id}/decide",
        json={"decision": "merge"},
        headers=anm_auth_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json() == {"id": str(review_id), "status": "merged"}
    assert len(await _aliases_for(candidate)) == 1


async def test_decide_keep_separate_repoints_nothing(client, anm_auth_headers):
    new_patient = await _insert_patient("KeepSeparate Test New Person", VILLAGE_B)
    candidate = await _insert_patient("KeepSeparate Test Candidate Person", VILLAGE_B)
    referral_id = await _insert_referral(new_patient, VILLAGE_B)
    review_id = await _insert_pending_review(new_patient, candidate)

    resp = await client.post(
        f"/identity/reviews/{review_id}/decide",
        json={"decision": "keep_separate"},
        headers=anm_auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"id": str(review_id), "status": "kept_separate"}

    async with async_session_factory() as session:
        referral_row = (
            await session.execute(
                text("SELECT patient_id FROM referral WHERE id=:id"), {"id": referral_id}
            )
        ).one()
        assert referral_row.patient_id == new_patient  # unchanged

        patient_row = (
            await session.execute(
                text("SELECT merged_into_id FROM patient WHERE id=:id"), {"id": new_patient}
            )
        ).one()
        assert patient_row.merged_into_id is None

    assert await _aliases_for(candidate) == []


async def test_merged_away_patient_excluded_from_future_blocking(client, anm_auth_headers):
    new_patient = await _insert_patient("Excluded Test New Person", VILLAGE_B)
    candidate = await _insert_patient("Excluded Test Candidate Person", VILLAGE_B)
    review_id = await _insert_pending_review(new_patient, candidate)

    resp = await client.post(
        f"/identity/reviews/{review_id}/decide",
        json={"decision": "merge"},
        headers=anm_auth_headers,
    )
    assert resp.status_code == 200

    async with async_session_factory() as session:
        candidates = await block(session, village_org_id=VILLAGE_B, phone=None)
    ids = {c.id for c in candidates}
    assert new_patient not in ids
    assert candidate in ids


DEVICE_TIME = datetime(2026, 8, 21, 9, 0, tzinfo=UTC).isoformat()


def _create_op(entity_id, patient_name, lamport):
    return {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "create_referral",
        "payload": {"patient_name": patient_name, "reason": "fever", "priority": "normal"},
        "lamport": lamport,
        "device_time": DEVICE_TIME,
    }


async def _push_accepted(client, headers, device_id, op):
    resp = await client.post(
        "/sync/push", json={"device_id": device_id, "ops": [op]}, headers=headers
    )
    result = resp.json()["results"][0]
    assert result["status"] == "accepted", result
    return result


async def test_a_kept_separate_pair_is_not_re_queued_by_a_later_push(
    client, auth_headers, anm_auth_headers
):
    # score(normalize(...), normalize(...)) == 84.0 — verified in the
    # review band under the real IDENTITY_AUTO_ACCEPT=92.0 /
    # IDENTITY_REVIEW_FLOOR=80.0 defaults.
    await _insert_patient("Requeue Test Jaikishan Rawal", VILLAGE_A)

    first_entity = uuid.uuid4()
    await _push_accepted(
        client, auth_headers, "d-requeue-1", _create_op(first_entity, "Requeue Test Jai Raval", 1)
    )
    async with async_session_factory() as session:
        first_patient_id = (
            await session.execute(
                text("SELECT patient_id FROM referral WHERE id=:id"), {"id": first_entity}
            )
        ).scalar_one()

    resp = await client.get("/identity/reviews", headers=anm_auth_headers)
    [row] = [r for r in resp.json()["reviews"] if r["new"]["id"] == str(first_patient_id)]
    await client.post(
        f"/identity/reviews/{row['id']}/decide",
        json={"decision": "keep_separate"},
        headers=anm_auth_headers,
    )

    second_entity = uuid.uuid4()
    await _push_accepted(
        client, auth_headers, "d-requeue-2", _create_op(second_entity, "Requeue Test Jai Raval", 1)
    )
    async with async_session_factory() as session:
        second_patient_id = (
            await session.execute(
                text("SELECT patient_id FROM referral WHERE id=:id"), {"id": second_entity}
            )
        ).scalar_one()

    # The second push found the first push's own provisional patient via
    # exact match — same patient reused, no second review queued.
    assert second_patient_id == first_patient_id

    async with async_session_factory() as session:
        reviews = (
            await session.execute(
                text("SELECT status FROM identity_review WHERE new_patient_id=:id"),
                {"id": first_patient_id},
            )
        ).all()
    assert [r.status for r in reviews] == ["kept_separate"]
