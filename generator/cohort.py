"""Cohort generator: the district, the patients, the duplicates, the name
variants. docs/PHASE7_PLAN.md P7.1 build order #3. Builds on
generator/names.py (NAME_VARIANT_GROUPS, the P6.1 table) rather than adding
a second one — FIRST_NAMES/LAST_NAMES are new, added to that same module,
for the bulk of genuinely distinct people who need no controlled variant
relationship at all.

Pure and deterministic: every function here takes `seed` and a resolved
config and returns plain dataclasses, with no I/O and no datetime.now() —
device times are the config's own simulated start plus generated offsets
(_BASE_TIME below). generator/cli.py is what checks "same seed twice ->
byte-identical", by running the whole CLI twice and diffing, not by
reasoning that purity implies it.

The org tree, per referral #7 in the session brief (ADR-005): each
generated village's referrals always target the one PHC that is its own
ancestor (village -> sub-centre -> PHC), the same shape app/seed.py's D4
fixture uses, scaled up. No generated referral ever names a facility
outside its own branch — a lateral referral would be invisible to the
facility that is supposed to receive it (ADR-005's own stated failure
mode), and this phase does not revisit that ADR.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import Random

from app.config import get_settings
from app.linkage.normalize import normalize
from app.linkage.scoring import score
from generator.names import FIRST_NAMES, LAST_NAMES, NAME_VARIANT_GROUPS

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)

REASONS: list[str] = [
    "fever, referred for evaluation",
    "antenatal checkup",
    "suspected tuberculosis",
    "diarrhea and dehydration",
    "injury, needs assessment",
    "hypertension follow-up",
    "malnutrition screening",
    "post-natal complication",
]
PRIORITIES: list[str] = ["urgent", "soon", "routine"]  # client/src/pages/CreateReferralPage.tsx


@dataclass(frozen=True)
class OrgUnitRow:
    org_id: uuid.UUID
    name: str
    type: str  # "PHC" | "SUB_CENTRE" | "VILLAGE" — free text column, no DB enum
    parent_id: uuid.UUID | None


@dataclass(frozen=True)
class UserRow:
    user_id: uuid.UUID
    name: str  # username, unique across app_user (uq_app_user_name) — namespaced by seed
    role: str  # "ASHA" | "ANM" | "MO"
    org_id: uuid.UUID


@dataclass(frozen=True)
class District:
    org_units: list[OrgUnitRow]  # written parent-first: PHCs, sub-centres, villages
    users: list[UserRow]
    village_org_id: list[uuid.UUID]  # index = village index
    village_name: list[str]  # index = village index
    village_asha: list[str]  # index = village index -> ASHA username
    village_target_org: list[uuid.UUID]  # index = village index -> ancestor PHC org_id
    facility_mo: dict[str, str]  # facility org_id (str) -> MO username


@dataclass(frozen=True)
class PatientRecord:
    record_id: uuid.UUID
    person_id: str
    name: str
    age: int
    sex: str
    phone: str | None
    village_index: int


@dataclass(frozen=True)
class ReferralSpec:
    referral_id: uuid.UUID
    patient_record_id: uuid.UUID
    origin_user: str
    target_org: uuid.UUID
    reason: str
    priority: str
    created_device_time: datetime


@dataclass(frozen=True)
class GroundTruth:
    seed: int
    patients: list[dict]
    queries: list[dict]


@dataclass
class Cohort:
    district: District
    patients: list[PatientRecord]
    referrals: list[ReferralSpec]
    ground_truth: GroundTruth
    redraws: int  # instruction #9 — how many name collisions were re-drawn


def _namespace(seed: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"nirantharseva.cohort.{seed}")


def _sid(ns: uuid.UUID, key: str) -> uuid.UUID:
    return uuid.uuid5(ns, key)


def build_district(seed: int, config: dict) -> District:
    """Facilities, sub-centres, villages, and the ASHA/ANM/MO users who
    staff them. Names are namespaced by seed so two cohort loads into the
    same database never collide (usernames need to be globally unique —
    uq_app_user_name), and never touch app/seed.py's own org names
    (never "PHC Ramnagar", "Sub-centre Kotwali", "Village A"/"B")."""
    ns = _namespace(seed)
    n_facilities = config["n_facilities"]
    n_villages = config["n_villages"]

    org_units: list[OrgUnitRow] = []
    facility_ids: list[uuid.UUID] = []
    subcentre_ids: list[uuid.UUID] = []
    users: list[UserRow] = []
    facility_mo: dict[str, str] = {}

    for f in range(n_facilities):
        org_id = _sid(ns, f"phc:{f}")
        facility_ids.append(org_id)
        org_units.append(OrgUnitRow(org_id, f"Cohort{seed} PHC {f + 1}", "PHC", None))
        mo_name = f"cohort{seed}_mo_{f + 1}"
        users.append(UserRow(_sid(ns, f"user:mo:{f}"), mo_name, "MO", org_id))
        facility_mo[str(org_id)] = mo_name

    for f in range(n_facilities):
        org_id = _sid(ns, f"subcentre:{f}")
        subcentre_ids.append(org_id)
        org_units.append(
            OrgUnitRow(org_id, f"Cohort{seed} Sub-centre {f + 1}", "SUB_CENTRE", facility_ids[f])
        )
        anm_name = f"cohort{seed}_anm_{f + 1}"
        users.append(UserRow(_sid(ns, f"user:anm:{f}"), anm_name, "ANM", org_id))

    village_org_id: list[uuid.UUID] = []
    village_name: list[str] = []
    village_asha: list[str] = []
    village_target_org: list[uuid.UUID] = []
    for i in range(n_villages):
        subcentre_index = i % n_facilities
        org_id = _sid(ns, f"village:{i}")
        name = f"Cohort{seed} Village {i + 1}"
        org_units.append(OrgUnitRow(org_id, name, "VILLAGE", subcentre_ids[subcentre_index]))
        asha_name = f"cohort{seed}_asha_{i + 1}"
        users.append(UserRow(_sid(ns, f"user:asha:{i}"), asha_name, "ASHA", org_id))
        village_org_id.append(org_id)
        village_name.append(name)
        village_asha.append(asha_name)
        village_target_org.append(facility_ids[subcentre_index])

    return District(
        org_units=org_units,
        users=users,
        village_org_id=village_org_id,
        village_name=village_name,
        village_asha=village_asha,
        village_target_org=village_target_org,
        facility_mo=facility_mo,
    )


def _combinatorial_name(index: int) -> str:
    """A plain `(index // len(FIRST_NAMES), index % len(FIRST_NAMES))` split
    gives the first 30 people (or, worse, every person in one village, since
    villages are assigned round-robin — same stride as FIRST_NAMES' own
    length would-be divisors) the identical surname or first name before
    the pool ever cycles. Scrambling `index` through a fixed multiplicative
    hash (Knuth's constant, truncated to 32 bits) before splitting it across
    the two pools decorrelates the name assignment from _assign_people's own
    round-robin village stride entirely, deterministically, with no RNG."""
    key = (index * 2654435761) % (2**32)
    first = FIRST_NAMES[key % len(FIRST_NAMES)]
    last = LAST_NAMES[(key // len(FIRST_NAMES)) % len(LAST_NAMES)]
    return f"{first} {last}"


def _phone(rng: Random, village_index: int, within_village_index: int) -> str | None:
    if rng.random() < 0.05:  # a real minority of records carry no phone (ADR-014)
        return None
    return f"9{village_index:02d}{within_village_index:05d}"


@dataclass
class _Person:
    person_id: str
    village_index: int
    canonical_name: str
    variant_name: str | None  # None unless this person came from a NAME_VARIANT_GROUPS entry
    age: int
    sex: str
    phone: str | None


def _assign_people(seed: int, config: dict, n_villages: int) -> tuple[list[_Person], int]:
    """One `_Person` per distinct human (not per record — duplicate_rate
    below decides which of these get a SECOND record). Returns the people
    and how many name collisions had to be re-drawn (instruction #9)."""
    rng = Random(seed)
    n_patients = config["n_patients"]
    duplicate_rate = config["duplicate_rate"]
    n_duplicates = round(n_patients * duplicate_rate)

    duplicate_indices = set(rng.sample(range(n_patients), k=min(n_duplicates, n_patients)))

    # Reserve NAME_VARIANT_GROUPS for duplicate people, one group per person,
    # cycling if there are more duplicates than groups (15) — tracked per
    # village so the same group is never reused twice in one village, which
    # would make two UNRELATED duplicate pairs share an identical name.
    group_used_in_village: dict[int, set[int]] = {v: set() for v in range(n_villages)}
    redraws = 0

    people: list[_Person] = []
    filler_cursor = 0
    for i in range(n_patients):
        village_index = i % n_villages
        age = rng.randint(1, 90)
        sex = rng.choice(["M", "F"])
        phone = _phone(rng, village_index, i)

        if i in duplicate_indices:
            used = group_used_in_village[village_index]
            group_index = i % len(NAME_VARIANT_GROUPS)
            attempts = 0
            while group_index in used and attempts < len(NAME_VARIANT_GROUPS):
                group_index = (group_index + 1) % len(NAME_VARIANT_GROUPS)
                attempts += 1
                redraws += 1
            used.add(group_index)
            spellings = NAME_VARIANT_GROUPS[group_index]
            canonical, variant = spellings[0], spellings[1 % len(spellings)]
            people.append(
                _Person(f"person:{i}", village_index, canonical, variant, age, sex, phone)
            )
        else:
            name = _combinatorial_name(filler_cursor)
            filler_cursor += 1
            people.append(_Person(f"person:{i}", village_index, name, None, age, sex, phone))

    return people, redraws


def _resolve_name_collisions(people: list[_Person], n_villages: int, review_floor: float) -> int:
    """Instruction #9: duplicate_rate's pairs must be the ONLY generated
    pairs scoring >= REVIEW_FLOOR within a village. Checks every pair of
    UNRELATED people (different person_id) sharing a village and re-draws
    a fresh combinatorial name for the loser when the check fails — the
    guard this session's brief calls for, made real rather than assumed.
    Returns the number of extra re-draws this pass needed, on top of the
    ones _assign_people already made for group reuse."""
    redraws = 0
    by_village: dict[int, list[int]] = {v: [] for v in range(n_villages)}
    for idx, p in enumerate(people):
        by_village[p.village_index].append(idx)

    fresh_cursor = len(people) + 1000  # never collides with _assign_people's own indices
    for _village_index, indices in by_village.items():
        # Re-check from scratch after any redraw in this village, since a
        # redraw can only ever lower a score, never raise a different pair's.
        changed = True
        guard = 0
        while changed and guard < 200:
            changed = False
            guard += 1
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    pa, pb = people[indices[a]], people[indices[b]]
                    if pa.person_id == pb.person_id:
                        continue  # the intended duplicate pair — allowed to score high
                    s = score(normalize(pa.canonical_name), normalize(pb.canonical_name))
                    if s >= review_floor:
                        name = _combinatorial_name(fresh_cursor)
                        fresh_cursor += 1
                        people[indices[b]] = _Person(
                            pb.person_id, pb.village_index, name, None, pb.age, pb.sex, pb.phone
                        )
                        redraws += 1
                        changed = True
    return redraws


def build_patients(
    seed: int, config: dict, district: District
) -> tuple[list[PatientRecord], GroundTruth, int]:
    """Patients (records) + ground truth. person_id groups records that are
    the same real human — two records per duplicate person, one per
    everyone else. Same shape as generator/gold_set.py's ground truth
    (patients + queries), adapted for record ids instead of DB patient ids
    since no row exists in the database until server/scripts/load_cohort.py
    replays these records through /sync/push (ADR-015 — the generator never
    writes to the database itself)."""
    n_villages = len(district.village_org_id)
    # Not a config field — the same operational floor app/linkage/pipeline.py
    # itself uses (Settings.identity_review_floor), so the generator's own
    # collision guard is checked against the exact threshold the real
    # pipeline will apply when the cohort is loaded.
    review_floor = get_settings().identity_review_floor
    name_variant_rate = config["name_variant_rate"]

    people, redraws = _assign_people(seed, config, n_villages)
    redraws += _resolve_name_collisions(people, n_villages, review_floor)

    rng = Random(seed + 1)  # separate stream from _assign_people's, still deterministic
    ns = _namespace(seed)

    patients: list[PatientRecord] = []
    gt_patients: list[dict] = []
    gt_queries: list[dict] = []

    for i, person in enumerate(people):
        record_id = _sid(ns, f"patient:{i}:0")
        patients.append(
            PatientRecord(
                record_id=record_id,
                person_id=person.person_id,
                name=person.canonical_name,
                age=person.age,
                sex=person.sex,
                phone=person.phone,
                village_index=person.village_index,
            )
        )

        if person.variant_name is None:
            continue  # not a duplicate person — one record only

        # The second ("return visit") record. With probability
        # name_variant_rate it uses the group's alternate spelling — a
        # genuine near-duplicate for E3 to find; otherwise it repeats the
        # exact same spelling, an exact-match duplicate instead.
        use_variant = rng.random() < name_variant_rate
        second_name = person.variant_name if use_variant else person.canonical_name
        second_id = _sid(ns, f"patient:{i}:1")
        patients.append(
            PatientRecord(
                record_id=second_id,
                person_id=person.person_id,
                name=second_name,
                age=person.age,
                sex=person.sex,
                phone=person.phone,
                village_index=person.village_index,
            )
        )
        gt_patients.append(
            {
                "record_id": str(record_id),
                "name": person.canonical_name,
                "village_index": person.village_index,
                "person_id": person.person_id,
            }
        )
        gt_queries.append(
            {
                "record_id": str(second_id),
                "name": second_name,
                "village_index": person.village_index,
                "expected_record_id": str(record_id),
                "person_id": person.person_id,
                "category": "duplicate_variant" if use_variant else "duplicate_exact",
            }
        )

    ground_truth = GroundTruth(seed=seed, patients=gt_patients, queries=gt_queries)
    return patients, ground_truth, redraws


def build_referrals(
    seed: int, config: dict, district: District, patients: list[PatientRecord]
) -> list[ReferralSpec]:
    """One or more referrals per patient record — D31's ~3 referrals per
    ~200 records (~600 total), a chronic patient referred more than once
    over the simulated period rather than one referral per record."""
    rng = Random(seed + 2)
    ns = _namespace(seed)
    referrals: list[ReferralSpec] = []

    for p_index, patient in enumerate(patients):
        origin_user = district.village_asha[patient.village_index]
        target_org = district.village_target_org[patient.village_index]
        n_referrals = rng.choices([1, 2, 3, 4, 5], weights=[15, 25, 30, 20, 10], k=1)[0]
        for r_index in range(n_referrals):
            referral_id = _sid(ns, f"referral:{p_index}:{r_index}")
            offset_days = rng.uniform(0, 300) + r_index * rng.uniform(10, 60)
            created = _BASE_TIME + timedelta(days=offset_days)
            referrals.append(
                ReferralSpec(
                    referral_id=referral_id,
                    patient_record_id=patient.record_id,
                    origin_user=origin_user,
                    target_org=target_org,
                    reason=rng.choice(REASONS),
                    priority=rng.choice(PRIORITIES),
                    created_device_time=created,
                )
            )
    return referrals


def build_cohort(seed: int, config: dict) -> Cohort:
    district = build_district(seed, config)
    patients, ground_truth, redraws = build_patients(seed, config, district)
    referrals = build_referrals(seed, config, district, patients)
    return Cohort(
        district=district,
        patients=patients,
        referrals=referrals,
        ground_truth=ground_truth,
        redraws=redraws,
    )
