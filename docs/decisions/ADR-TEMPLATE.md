# ADR-NNN: <short title of the decision>

**Destination:** `docs/decisions/ADR-TEMPLATE.md` — copy it to `ADR-001.md`,
`ADR-002.md` and so on. Never renumber and never rewrite a decided ADR; if the
decision changes, write a new ADR and mark the old one superseded.

**Why these exist:** these are the paragraphs you will paste into Chapter 3, and
they are the questions a sharp panel member asks. Writing them at the moment of
the decision takes ten minutes. Reconstructing them in week 10 takes an afternoon
and reads like it.

---

**Status:** Proposed | Accepted | Superseded by ADR-NNN
**Date:** YYYY-MM-DD
**Decided by:** user | Claude Code (small technical choice)

## Context

What situation forced a decision. Two or three sentences. State the constraint
that made it non-obvious — usually time, the offline requirement, the experiment
design, or the review calendar.

## Decision

What was chosen. One paragraph, in the active voice: "The system injects a Clock
protocol rather than calling `datetime.now()` directly."

## Alternatives considered

At least one real alternative, with the reason it lost. An ADR with no rejected
alternative is not a decision, it is a note.

| Option | Why not |
|---|---|
| | |

## Consequences

What this makes easy, and what it makes hard or impossible later. Be honest about
the cost — a stated cost is a defence, an unstated one is a hole. Where the cost
is measurable, say how it will be measured (for example, "the sequencing lock's
effect on p95 write latency is reported in E5").

## Which invariant this protects

I1–I7, or "none — this is a convenience decision".

---

## Already decided — write these two first, in Phase 0

- **ADR-001** — the injectable clock. Why the system never calls `datetime.now()`,
  and how a 120-hour SLA experiment runs inside a ten-week project.
- **ADR-002** — serialised sequence assignment with a transaction-scoped advisory
  lock. Why sequence order must equal commit order, what the pull cursor does
  without it, and the write-latency cost that E5 will report.

These two are the decisions a panel is most likely to probe.
