# Demo script

The click path for a live walkthrough. `server/scripts/demo.sh`
(`make demo`) resets the stack and prints a condensed version of this at
the terminal — read this file while rehearsing; read the terminal output
while presenting. Written for P9.1 (`docs/PHASE9_PLAN.md`, D46–D49).

Total time: **about 4 minutes** for the six steps below, plus however long
you spend talking. The one timing constraint that matters: **do step 2
before you've used up more than about a minute on step 1**, so its referral
has time to breach while you're still doing steps 3–5 (see "The headline
moment" below).

## Before you start

Run `bash server/scripts/demo.sh` and leave its terminal output visible —
it prints every login and confirms the demo-scale scheduler is running.

**Use a separate browser window (or profile/incognito) per role.** The
session token lives in `localStorage`, which is shared by every tab of the
same browser profile — logging in as a second user in another tab of the
*same* window silently replaces the first login. Four windows, logged in
once each and left alone, is simpler than logging in and out mid-demo:

1. Window **A** — `asha_a` / `dev`
2. Window **B** — `mo1` / `dev`
3. Window **C** — `anm1` / `dev`
4. Window **D** — `supervisor1` / `dev`, on `/supervisor` — **open this one
   first and never touch it again.** It is what step 6 comes back to.

## The headline moment

§8 of `docs/IMPLEMENTATION_PLAN.md` calls this the twenty seconds a panel
will remember: a referral breaches its SLA and appears on the supervisor
dashboard **with no page reload**, because window D has had an open
`EventSource` connection to `/dashboard/stream` the entire time. The demo
scheduler is scaled (`SLA_SCALE=0.0004`) so a 24-hour SLA breaches in about
35 seconds — the referral you create in step 2 will flip from "on the way"
to "overdue" in window D while you are still doing steps 3–5 elsewhere.
**Verified in rehearsal: it flipped at exactly 35 seconds, live, no
reload.** Glance at window D after step 5 and it should already have
happened; if it hasn't, keep talking for another 15–20 seconds and it will.

**At this scale, everything breaches fast, not just step 2's referral.**
Rehearsal also showed this: by the time window D was opened a couple of
minutes after `demo.sh` finished, *five* referrals were already overdue —
not only Suresh Yadav (seeded overdue on purpose) but also the two fixture
referrals from `app.seed` (Lakshmi Devi, Fatima Begum) and Ramesh Kumar
himself, all breached on their own in the gap between seeding and opening
a browser. This is the setting working as intended, not a problem to fix —
say so if the dashboard has more red rows than you expected when you first
look at it. The one thing this *does* affect: if you take more than about
a minute between running `demo.sh` and starting step 4, Ramesh Kumar may
already show "overdue" before the MO ever touches him. `mo1` can still
advance an already-overdue referral — GUARDS allows ESCALATED→ARRIVED same
as IN_TRANSIT→ARRIVED — and doing so resolves the escalation either way, so
nothing breaks. If it happens, say so out loud: it's D22's resolve-on-exit
behaviour, and it's a legitimate second demo point, not a miss.

## The six steps

**1. Window A, `/referrals` — the ASHA's own list (~30s)**
Already has referrals from `demo.sh`'s seeding (Lakshmi Devi from the
fixture district, Ramesh Kumar on the way, a provisional Lakshmy Devi still
under review). Say: this is read entirely from the phone's own local
storage — it looks the same with the network off.

**2. Window A, `/referrals/new` — create one more referral (~40s)**
Fill in a name (anything), a reason, and save. **This is the referral you
watch breach in step 6** — its clock starts the moment you save it, so do
this early. Point out the "saved on your phone" confirmation and, if you
want to make the offline point explicitly, use DevTools' offline checkbox
first (see "Fallbacks" below — this is the same mechanism).

**3. Window A, `/referrals/:id` — open the one you just created (~20s)**
Show the timeline: one entry, "Created," with who and when. This is the
same append-only event log every other screen reads from.

**4. Window B, `/mo/incoming` — advance Ramesh Kumar (~30s)**
"On the way" tab, tap the action button to move him to "Arrived." Say: one
tap, and the ASHA's own screen (window A, if you flip back to it) updates
without her doing anything. If his card already shows "overdue" (see the
note above), advance him anyway — it still works, and resolves the
escalation on the spot.

**5. Window C, `/identity-review` — decide the Lakshmy/Lakshmi pair (~40s)**
"Existing record" vs. "New referral," the name boxed because it differs.
This pair scores in the review band on purpose — close enough to flag,
not close enough to auto-merge. Pick either button; both are real, both
resolve the queue.

**6. Window D, `/supervisor` — the payoff (~30s + however long you wait)**
Point at the dashboard: Suresh Yadav's referral is already there, seeded
overdue by `demo.sh` so this screen was never empty — and by now there may
be several other rows too (see the note above; that's expected). Then find step 2's
referral — it should already have flipped to overdue on its own, live, in
this same window you never reloaded. If the timing worked out, narrate the
flip as it happens instead of pointing at something already-flipped — say
so out loud either way ("watch — this one's about to breach" vs. "this one
just did, while we were on the MO screen").

## Fallbacks

Ranked by P7.3 (C5); reuse this list, don't invent a second one.

1. **Browser DevTools "offline" checkbox** — the primary path for proving
   offline creation works. Instant, reliable, and the exact mechanism the
   Playwright suite itself uses (`context.setOffline(true)`).
2. **`docker compose stop api`** — the browser still believes it has a
   network, so the outbox's retry path actually runs. This is the same
   fault this project's E4 fault-injection test exercises with a real
   `docker kill`.
3. **A real phone, airplane mode, added to home screen** — fallback of
   last resort; needs the recorded clip (`docs/IMPLEMENTATION_PLAN.md`
   §8.5), not a live browser.

If the live escalation itself doesn't fire in time: it means the demo
scheduler isn't running (`docker ps` for `demo-scheduler`) or the 35-second
window hasn't elapsed yet — keep narrating steps 3–5 a little longer, it
will not fail to happen, only be late.

## Afterward

```bash
docker stop demo-scheduler
```

It was started with `--rm`, so stopping it also removes it. Leaving it
running keeps sweeping every 5 seconds against demo-scale SLAs — harmless,
but noisy in `docker ps` and in the logs if you're about to do something
else with this stack.
