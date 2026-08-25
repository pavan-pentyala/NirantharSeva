# Recording script — the two-minute demo clip

`docs/IMPLEMENTATION_PLAN.md` §14's third fallback (after local Compose and
— deliberately, ADR-018 — instead of a deployed URL): a recorded clip that
stands on its own if a live demo can't run during the review. This is a
**shot list for recording and editing**, not a live walkthrough — unlike
`docs/DEMO_SCRIPT.md` (which is longer, narrated, and meant to be *watched
live*), this is cut for a fixed ~2-minute runtime and assumes you'll trim
in post.

**Every mechanism below was independently verified working in P9.1's real
browser rehearsal** (`docs/PHASE9_PLAN.md`, PROGRESS.md's P9.1 entry) —
the offline save, the MO advance, the identity-review merge, and the
live escalation flip at exactly 35 seconds. This document only reorders
and re-times those same proven actions for video; it does not introduce
any click path P9.1 didn't already exercise.

## Before recording

```bash
bash server/scripts/demo.sh
```

Read its printed output once — the demo-scale scheduler needs to already
be running before shot 4 below, which `demo.sh` guarantees. Keep its
terminal visible or note the URLs/logins; you won't have time to look
them up mid-recording.

Open four browser windows ahead of time, logged in once each (session
tokens are shared per browser profile — see `docs/DEMO_SCRIPT.md`'s own
note on this): `asha_a`, `mo1`, `anm1`, `supervisor1` on `/supervisor`.
Arrange them so you can cut between windows quickly (separate monitor,
or a screen-recording tool that can switch capture sources).

## Shot list

Budget: 120s total. Running time shown is cumulative.

| # | 0:00 mark | Shot | What to show |
|---|---|---|---|
| 1 | 0:00–0:10 | Title card or opening line | "NirantharSeva — a referral doesn't get lost because a phone loses signal." Optionally show the login screen (no role chips — this is a deliberate design point if you want one sentence on it). |
| 2 | 0:10–0:30 | Window A (`asha_a`), DevTools offline checkbox ON, `/referrals/new` | Fill in a referral, save. Show the "saved on your phone / no signal right now" confirmation. This is the primary offline path (P7.3's own C5 ranking) — the same mechanism the Playwright suite itself uses. |
| 3 | 0:30–0:40 | DevTools offline OFF | Cut to the outbox flushing — a quick glance at Window A's referral now showing "synced," or skip straight to shot 4 if the sync is too quick to catch on camera. |
| 4 | 0:40–1:20 (40s) | Window D (`supervisor1`, already open, never reloaded) | **The headline shot.** The referral from shot 2 flips from normal to "overdue" live, no reload — confirmed in rehearsal to happen at ~35s after creation. If your recording software supports it, speed up this segment 2× in editing rather than cutting away — the point is durationally real, not simulated, and cutting it short undersells it. |
| 5 | 1:20–1:40 | Window B (`mo1`), `/mo/incoming` | Tap the advance button on a card. One tap, done. |
| 6 | 1:40–1:55 | Window C (`anm1`), `/identity-review` | Show the boxed disagreeing name field, tap either decision button. Cut this shot first if you're over budget — it's the weakest link to the headline story. |
| 7 | 1:55–2:00 | Closing card | "Demonstration system — synthetic data only" (already on every screen) or a one-line summary. |

## Fallback ranking, if a shot doesn't cooperate on the day

Reuse P7.3(C5)'s own ranking (`docs/DEMO_SCRIPT.md` has the full text) —
don't invent a second list:

1. Browser DevTools "offline" checkbox (shot 2's own mechanism).
2. `docker compose stop api` — exercises the retry path if you want a
   fault-tolerance beat instead of the offline one.
3. The real phone (see `docs/RECORDING_PHONE_CLIP.md`) — a different
   clip entirely, not a substitute shot within this one.

## Afterward

```bash
docker stop demo-scheduler
```
