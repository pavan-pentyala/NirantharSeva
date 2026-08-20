# UI design brief

**Destination:** `docs/UI_DESIGN_BRIEF.md`

**Status:** Filled in and confirmed. The design bundle this brief points to has
arrived (`docs/design_handoff_ui_screens/`) and Phase 4 is planned against it —
see `docs/PHASE4_PLAN.md`.

---

## 1. Reference images or links

Designed from scratch, no external references. The design files — `Design
System.dc.html`, `Screen 1`–`Screen 7` (`.dc.html`), and this brief's source
copy — have arrived and live in `docs/design_handoff_ui_screens/`. Open any
`.dc.html` file directly in a browser to view it (each loads `support.js`
from the same folder).

## 2. Overall feeling

- [x] Clinical and plain, with one warm touch: square sheets, hairline rules,
  dense rows, monospace numbers, one blue accent (from the "clinical"
  direction) — but state labels are rounded pills in plain language (from the
  "warm" direction). Two directions were shown side by side and this is the
  chosen mix. Not government-service style.

## 3. Colour

- Primary colour: `#32679b` (oklch(0.5 0.1 250)) — the only interface accent;
  means "the app", never a patient state.
- Ink: `#171a1e` (headings/body), `#484e53` (secondary), `#65686e` (meta/timestamps).
- Sheet: `#ffffff`; sheet-2 (headers/groups): `#f2f4f8`; hairline `#dee3e4` / `#ced1d4`.
- Colours to avoid: red (`#b33637`) is reserved only for Escalated/overdue —
  never decorative. Amber (`#8b5601` on `#fef1d4`) is reserved only for "saved
  here, not sent yet" — never a medical meaning.
- State colours: one treatment per state (see §7 in the design system doc),
  grouped into three visual families — fine / overdue / done — see next
  section.

## 4. Type

- Font: device default only — `system-ui` (renders as Roboto on the ASHA's
  Android phone). No downloaded fonts. Numbers that must align (times, counts,
  phone numbers) use `ui-monospace`.
- Devanagari/Tamil: not needed — English only, per scope.

## 5. Screens you know you want

Seven screens, designed and built as `.dc.html` files in
`docs/design_handoff_ui_screens/` (see §1):

**ASHA (phone):**
- My referrals list — 3 states shown: online/synced, offline with 3 updates
  waiting, empty (`Screen 1 - ASHA My Referrals.dc.html`)
- Create referral — form + saved-offline confirmation
  (`Screen 2 - ASHA Create Referral.dc.html`)
- Referral detail and timeline — normal + escalated version
  (`Screen 3 - Referral Detail.dc.html`)

**ANM:**
- Identity review queue — side-by-side match, differing fields highlighted
  (`Screen 6 - ANM Identity Review.dc.html`)

**MO (tablet):**
- Incoming referrals — one-tap state changes on the card, no detail screen
  needed (`Screen 5 - MO Incoming Referrals.dc.html`)

**Supervisor (desktop):**
- Live dashboard — counts by state + overdue list, steady state and the
  moment a new breach lands (`Screen 4 - Supervisor Dashboard.dc.html`)

**All roles:**
- Login — phone number, PIN, role picker (`Screen 7 - Login.dc.html`)

Anything beyond these seven, Claude Code proposes and the user approves.
All seven are HTML design references, not production code — recreate them in
the project's actual stack (React 18 + TypeScript + Vite, reading from
Dexie.js, per `CLAUDE.md`), don't embed the HTML.

## 6. The offline indicator

- Lives in a band directly under the header on every worker screen (not
  floating, not a separate bar) — the first thing under the page title.
- Offline with work pending: amber band, dot, "No signal" / "3 updates waiting
  to send. They will send when signal comes back." / monospace "Last sent
  today 9:14 am" underneath.
- Fully synced: neutral grey band, dot, "Connected" / "Everything is sent." /
  "Last sent 2 minutes ago".
- Row-level: any referral holding an unsent change also carries its own small
  "Waiting to send" pill next to its state.
- Banned words anywhere in copy: sync, pending ops, conflict, operation,
  queue, offline mode, retry, payload.

## 7. The escalation moment

- Appears, does not animate in aggressively: on the dashboard, a new overdue
  row's background fades from a pale red to plain white over ~2 seconds while
  everything else on screen stays still; the overdue count and a one-line
  banner update in place at the same time. No motion elsewhere, no colour
  flash on unrelated rows.
- Sound: none.
- "Overdue by 2 hours" vs "overdue by 2 days": both use the identical red
  pill + left border treatment — severity is not colour-coded further. The
  overdue list is simply sorted by how overdue, worst first, and each row
  states the plain duration ("2 days", "19 h", "40 min"). This keeps the
  signal legible in bright light without adding a second colour scale.

Sunlight/no-colour fallback: every referral group is carried by pill *shape*
first, colour second, and a word always — fine = filled soft pill, overdue =
solid dark pill with a "!" mark and a 4px left bar, done = outline-only pill
with a ✓/✕. Confirmed to hold up in greyscale (see §7 of the design system).

## 8. Hard constraints — these are not negotiable

Claude Code follows these even if the rest of this file is empty.

- Mobile-first. The ASHA is on a cheap Android phone in a village.
- Big touch targets. Creating a referral is the most frequent action and must be
  the shortest path.
- Works in daylight — high contrast, readable at arm's length.
- Low bandwidth. No heavy images, no large font downloads, no animation used to
  cover latency.
- The interface reads only from the local cache, so it looks identical online and
  offline. No separate "offline mode" screens.
- A visible "Demonstration system — synthetic data only" marker.
- Once the design direction is set, it stays. No restyling in a later phase
  without asking.
