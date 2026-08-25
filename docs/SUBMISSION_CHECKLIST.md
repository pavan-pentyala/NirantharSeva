# Submission checklist — Review-III

Every deliverable §14 (`docs/IMPLEMENTATION_PLAN.md`) and the phase map's
P9 row point at, and its actual state as of P9.3 (2026-08-25). Not a
report — a status table, so nothing is discovered missing at submission.

## Ready now

| Deliverable | State |
|---|---|
| Local live demo | Ready. `bash server/scripts/demo.sh` + `docs/DEMO_SCRIPT.md`, rehearsed cold end-to-end in a real browser (P9.1). Primary demo path per §14. |
| Two-minute demo clip — shot list | Ready to record. `docs/RECORDING_DEMO_CLIP.md`. Every shot's underlying mechanism independently verified working (P9.1's rehearsal). Recording itself not done — needs a screen recorder and ~20 minutes. |
| Real-phone airplane-mode clip — shot list | Ready to record, with the technical setup (built app on `:4173`, `adb reverse` for a real secure context) verified server-side this session. `docs/RECORDING_PHONE_CLIP.md`. Recording itself not done — needs a physical phone (§8.5, kept on the list since it was first flagged; do not drop it). |
| Deployed URL | **Deliberately not built** — ADR-018/D43. §14 asks for "all three" (local, deployed, recorded); this project ships two of three on purpose, with a written decision record for the third. If asked: point at ADR-018, not at a gap. |
| Production-ready configuration | `docker-compose.prod.yml`, brought up and verified serving (P9.2) — a concrete answer to "could this be deployed?" without an actual deployment. |
| The advisory lock's measured cost | `server/results/e5_lock/summary.md` — the §3-promised sentence, with a number (P9.2). |
| All six experiments (E1–E6) | Complete, results committed, `server/results/e1`–`e6` (Phase 8). |
| Server test suite | 269 passed, `alembic heads` at `0009`. |
| Client test suite | 11 Playwright specs, all seven screens real (no placeholders since P6.2). |
| Architecture decision records | ADR-001 through ADR-018, `docs/decisions/`. |
| README.md | Rewritten against the running system, verified line by line (P9.1). |
| `docs/OBSERVATIONS.md` | 63 numbered, hard-won findings, one append-only log across every phase. |

## Owed — needs your own hands, not another session

| Deliverable | State |
|---|---|
| The two-minute demo clip (the recording itself) | Shot list ready; not recorded. |
| The real-phone clip (the recording itself) | Shot list ready; not recorded. Needs a phone, ideally Android with USB debugging for the cleanest setup (`docs/RECORDING_PHONE_CLIP.md`). |
| Weekly minutes of meeting | `docs/mom/` holds only a `.gitkeep` — ten weeks, zero files. These are records of real meetings with your guide; they belong to you, not to a session. Flagged here only so it isn't discovered missing at submission. |

## Deferred on purpose — not owed to Phase 9

| Deliverable | State |
|---|---|
| The written report | Deferred until after Phase 9 (D42) — your own plan, to be shared once Phase 9 completes. Nothing report-shaped was created, scaffolded, or outlined in this repository during Phase 9, on purpose. |
| Appendix B (paper submission) | `docs/IMPLEMENTATION_PLAN.md` §14: "confirm with your guide whether mandatory for this course before spending time on it." Still an open question only you can resolve — not started either way. |

## Small and optional — not done, flagged rather than assumed

| Deliverable | State |
|---|---|
| Appendix A's OpenAPI export | The spec is already live and correct at `http://localhost:8000/openapi.json` (FastAPI generates it automatically) — just not yet saved to a file in the repo. Trivial if you want it: `curl http://localhost:8000/openapi.json -o docs/openapi.json`. Not done this session — outside P9.3's stated scope (recording scripts + this checklist), not because it's hard. |

## If a panel member asks about something not on this list

`docs/PROJECT_REFERENCE.md`'s "Where to look when the panel asks about X"
table (gitignored, for your own prep) indexes the ADR/code/observation
that answers most likely questions, including the two this project
expects to be probed hardest on (§3's own callout): the advisory lock's
now-measured cost, and what actually responds to an escalation in the
simulation (ADR-017).
