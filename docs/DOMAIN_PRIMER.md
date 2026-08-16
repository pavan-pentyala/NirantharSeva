# Domain primer — the referral ladder

**Destination:** `docs/DOMAIN_PRIMER.md`

**Why this exists:** the implementation plan is precise about the engine but does
not explain the health system it models. Claude Code will write screen labels,
role names, error messages, and seed data, and a panel of examiners will read
them. Wrong vocabulary looks careless even when the code is correct.

---

## The people

**ASHA** — Accredited Social Health Activist. A community health worker based in
a village, usually the first point of contact. She identifies a patient who needs
care beyond the village and starts the referral. In this system she is the
originator of most referrals and the person who closes the loop when the patient
comes back. She works on a cheap phone, often with no signal. **She is the primary
user, and the offline-first design exists for her.**

**ANM** — Auxiliary Nurse Midwife. Staffs a sub-centre, which serves several
villages. Sits above the ASHA, supervises several of them, and handles the review
queue for uncertain patient identity matches.

**MO** — Medical Officer. A doctor at a PHC or above. Records that the patient
arrived, that treatment happened, and that the patient is being sent back down.
Only the MO can move a referral through the clinical states.

**Supervisor** — sees the dashboard, receives escalations, and acts when a
referral has breached its deadline. Does not do clinical work in this system.

## The places

The ladder runs upward:

**Village** (ASHA) → **Sub-centre** (ANM) → **PHC**, Primary Health Centre →
**CHC**, Community Health Centre → **District Hospital**.

These are modelled as `org_unit` rows in a tree. Visibility follows the tree: a
user sees their own unit and everything below it, never sideways. An ASHA in
village A must not see a referral from village B — that rule is enforced in the
API and in `/sync/pull`, and a pull that ignores it is a data leak that the UI
will not reveal.

## The problem being solved

A patient is referred upward and then nobody owns what happens next. There is no
clock on it, no single person responsible, and no record that closes. The patient
drops out somewhere between two levels and nobody notices — this is the
"loss to follow-up" the report is about. The system's answer is to make the
referral a tracked object with a state, an owner, and a deadline, and to escalate
automatically when the deadline passes.

## The states, in plain terms

| State | Means |
|---|---|
| `CREATED` | ASHA has written the referral; patient has not left yet |
| `IN_TRANSIT` | Patient is on the way to the facility |
| `ARRIVED` | Facility has confirmed the patient reached them |
| `TREATED` | Care was given |
| `BACK_REFERRED` | Patient sent back down to the village for follow-up |
| `CLOSED` | Loop complete — ASHA has confirmed the patient is back and followed up |
| `ESCALATED` | A deadline was breached; a supervisor has been notified |
| `LOST` | Declared unrecoverable after escalation |

`CLOSED` is the outcome the whole project is measuring. `ESCALATED` is not a dead
end — a referral returns from it to the normal path, which is what makes
escalation a supervisory signal rather than a separate workflow.

## Words to use in the interface

Write for a health worker, not for a developer. Users never see "operation",
"sync conflict", "idempotent", or "Lamport". They see plain descriptions of what
happened and what to do next.

| Do not show | Show instead |
|---|---|
| "3 ops pending in outbox" | "3 updates waiting to send" |
| "Sync conflict detected" | "Someone else updated this. A supervisor will check." |
| "Op rejected: guard violation" | "Only a doctor can mark this as treated." |
| "State transition invalid" | "This referral cannot move to that step yet." |
| "SLA breach" | "Overdue — no update for 2 days" |

Keep the eight state names in the interface, since they are the vocabulary of the
project and the report, but pair each one with a short plain-language line the
first time it appears on a screen.

## Names in test and demo data

The identity-resolution work depends on realistic Indian name variation —
Lakshmi / Lakshmy / Laxmi, Krishnan / Krishnnan, Muhammad / Mohammed / Mohamad.
Build the variant rules by hand from a small table. Do **not** use random
character noise: it produces mistakes no human would ever make, and it makes the
fuzzy matcher look better than it is, which shows up as an indefensible number in
Chapter 4.

Demo and seed data should look like a real district: a handful of villages under
a sub-centre, a PHC above them, plausible names, plausible ages. A panel reads
the demo screen before it reads the code.

## The ethical boundary — state it in the interface

All data is synthetic. There is no government dataset and no real patient
information anywhere in this project, by explicit choice. Keep a visible marker
in the interface — a small banner or footer reading "Demonstration system —
synthetic data only". It costs nothing and it answers a question the panel would
otherwise ask.
