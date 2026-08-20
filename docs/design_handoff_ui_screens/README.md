# Handoff: NirantharSeva UI screens

## Overview
Seven core screens for NirantharSeva, an offline-first referral tracking app
for India's rural public-health system, plus the design system they're built
from. Covers all four roles: ASHA (phone), ANM (tablet), MO (tablet), and
Supervisor (desktop).

## About the design files
The `.dc.html` files in this bundle are **design references built in HTML** —
static prototypes showing intended look, layout, copy, and (for the
dashboard) one animated state, not production code to copy directly. Open any
file directly in a browser to view it. The task is to **recreate these
designs in the target codebase's stack** (per the project's `CLAUDE.md`:
React 18 + TypeScript + Vite, reading from Dexie.js/IndexedDB, syncing via the
FastAPI backend) using that stack's own component patterns — not to embed or
ship this HTML as-is.

## Fidelity
**High-fidelity.** Colors, type sizes, spacing, and copy below are final —
recreate pixel-close using the values in this document and in
`Design System.dc.html`. The one interaction spec (§7, dashboard escalation)
should be built as described; nothing else in these files carries motion.

## Design system
Full system lives in `Design System.dc.html`. Values below are the ones an
implementer needs; everything else in the file is illustrative.

### Colors
| Token | Value | Use |
|---|---|---|
| ink-900 | `#171a1e` | names, headings, body |
| ink-700 | `#484e53` | secondary text |
| ink-500 | `#65686e` | meta, timestamps |
| sheet | `#ffffff` | every screen background |
| sheet-2 | `#f2f4f8` | headers, footers, grouped bands |
| hairline | `#dee3e4` | row divider |
| rule | `#ced1d4` | section divider, borders |
| accent | `#32679b` | buttons, links, active tab — means "the app", never a patient state |
| waiting (text/bg) | `#8b5601` / `#fef1d4` | "not sent yet" only, never medical |
| alert | `#b33637` | Escalated/overdue only, nothing else |

State-family fills (see full table in Design System §5 / brief §7):
fine states use pale tinted pill fills (`#e4e9eb`/`#484e53` Created,
`#d4ebff`/`#254e77` In transit, `#ceeef9`/`#105767` Arrived,
`#cdf3e1`/`#0b553c` Treated, `#ede2fe`/`#5d4980` Back referred); Escalated is
solid `#b33637` fill with white text; Closed/Lost are white with a 1.5px
outline (`#144432` / `#2b2f33`) and a ✓/✕ mark.

### Type
System font stack only: `system-ui, -apple-system, "Segoe UI", Roboto,
sans-serif` (renders as Roboto on Android). No downloaded fonts. Numbers that
must align — times, counts, phone digits — use `ui-monospace, Menlo, monospace`.

Scale: display 25px/650, title 20px/650, name 19px/650, body 16px/400,
secondary 14.5px/400, label 13.5px/650, meta 13px mono, demo marker 11px.
Body text never below 14.5px.

### Spacing, radius, touch
Base unit 4; steps used: 4, 8, 12, 16, 24, 32, 40. Screen edge padding 16 on
phone, 24 on tablet/desktop.
Two radii only: `4px` for sheets/rows/buttons/inputs, `100px` for state pills
and filter chips.
Minimum tappable target 48×48. List rows ≥72 tall. Primary button 56 tall,
full width, 16 from screen edge.

### The three-shape rule (sunlight/greyscale-safe)
Every referral's group is carried by pill **shape** first, colour second, a
word always — required because colour is the first thing lost in direct
sunlight:
- **Fine** — filled soft pill, pale tint, no border, dark text.
- **Overdue** — solid dark red pill, white bold text, round "!" mark, plus a
  4px red bar down the row's left edge.
- **Done** — no fill, 1.5px outline border, a ✓ (Closed) or ✕ (Lost) mark.

### Copy rules for the sync indicator
Use: waiting to send · sent · no signal · connected · saved on this phone ·
needs a check.
Never use: sync, pending ops, conflict, operation, queue, offline mode,
retry, payload.

## Screens

### 1. ASHA — My referrals (`Screen 1 - ASHA My Referrals.dc.html`)
Phone, 390×844 reference frame. Three states shown side by side — build all
three as one screen driven by real connection/data state, not three routes.
- **Layout, top to bottom:** 11px grey demo marker band → header (24px "My
  referrals" title + role chip, 14.5px worker name/village line) → sync band
  (see below) → three-tab filter row (All / Need a check / Done, each with a
  live count, active tab has 2px accent underline) → scrollable list of rows
  → fixed footer with 56px full-width primary button "New referral".
- **Sync band:** icon dot (12px circle) + 15.5px bold status line + 14px
  detail line + monospace 12.5px last-sent time. Amber fill (`#fef1d4`
  background, `#8b5601` dot) when offline with items waiting; grey fill
  (`#f2f4f8`, `#0b553c` dot) when connected/synced.
- **List row:** name (19px, 700 weight if overdue else 650), monospace
  age-in-state top right, secondary line (age/sex · reason · facility, 14.5px
  `#484e53`), then a row of pills: the state pill, plus a "Waiting to send"
  pill (`#fef1d4`/`#8b5601`) if this row holds an unsent change. Overdue rows
  get the 4px left red bar.
- **Empty state:** centered dashed-circle placeholder, 18px "No referrals
  yet" heading, one line of body copy, same footer button.

### 2. ASHA — Create referral (`Screen 2 - ASHA Create Referral.dc.html`)
Phone. Single-screen form, no multi-step wizard — this is the highest-
frequency action and must be the shortest path.
- **Fields, in order:** Patient name (text, 52px input) · Age (number) + Sex
  (2-button toggle) side by side · Phone number (text, optional) · Village
  (pre-filled to the ASHA's own village, shown greyed with an "yours" tag) ·
  Reason for referral (text) · How urgent (3-way pill toggle: Urgent/Soon/
  Routine, Urgent defaults selected and uses the alert red) · Sending to
  (pre-filled facility chip with a "change" affordance).
- **Footer:** 56px primary button "Save referral".
- **Saved-offline confirmation (same screen, post-save state):** replaces
  the form with a centered green check circle, "Referral saved" (22px), one
  line naming the patient, then an amber info card: "No signal right now —
  it will send by itself when your phone finds signal. You do not need to do
  anything." Two footer buttons: primary "Back to my referrals", secondary
  outline "Add another referral". This confirmation must appear identically
  whether the save happened online or offline — only the sync band on the
  next screen differs.

### 3. Referral detail and timeline (`Screen 3 - Referral Detail.dc.html`)
Phone. One referral: header with back arrow + patient name, a summary block
(demographics, reason, facility, state pill, monospace time-in-state, and a
plain-language deadline line), then a vertical timeline (dot + connector +
event title + "when · by whom" line, oldest at bottom, a hollow dot for the
still-pending next step), then a fixed footer with the one action available
to this user right now (e.g. "Mark as arrived").
- **Escalated version:** summary block gets the 4px red left bar and an
  additional red-tinted explanation card in plain language ("He was expected
  to arrive by 2:00 pm yesterday. No update has come since he left. The
  supervisor has been told."). Timeline gets one extra top entry: "Marked
  overdue — supervisor told" in red, attributed to "the system". Footer
  gains a second, secondary-outline escape action ("I could not reach him —
  mark as lost").

### 4. Supervisor — live dashboard (`Screen 4 - Supervisor Dashboard.dc.html`)
Desktop, 1360px reference width. Most important screen — must update without
a page refresh.
- **Layout:** header (block name, supervisor name, live dot + "updated N
  seconds ago") → 6-column stat strip (Open / On the way / Reached centre /
  Treated-sent back / **Overdue**, in the alert colour with a red left
  border / Closed this month) → "Overdue — act now" list, sorted worst-first,
  columns: Patient, Village, Sent to, Reason, Overdue by (monospace, red),
  ASHA. Every row carries the 4px red left bar.
- **Interaction spec — the escalation moment:** when a new breach arrives,
  insert its row at the correct sorted position with a background that
  starts pale red (`#fdeceb`) and fades to white over **~2 seconds**
  (`ease-out`), while nothing else on screen moves or flashes. Simultaneously:
  the Overdue stat count increments in place, and a one-line dismissible
  banner appears directly under the header ("New overdue referral: —
  no update for N past deadline"). **No sound.** Severity is not
  colour-coded further — "overdue by 2 hours" and "overdue by 2 days" use the
  identical pill and bar treatment; only the sort order and the plain-text
  duration communicate how bad it is.

### 5. MO — incoming referrals (`Screen 5 - MO Incoming Referrals.dc.html`)
Tablet, 834px reference width. Optimized for ~30 seconds per patient: every
state change happens with one tap directly on the card, no drill-in to a
detail screen.
- **Layout:** header + sync indicator → 3-tab filter (On the way / At the
  centre / Treated today, each with a count) → list of cards: name + age +
  reason/referrer line + state pill (with overdue treatment where relevant)
  on the left, one large 52px action button on the right whose label always
  matches the next state ("Arrived" for in-transit cards, "Treated" for
  arrived cards). A second tap after "Treated" should offer "Sent back to
  ASHA" — implement as the same one-button-per-card pattern advancing again.

### 6. ANM — identity review queue (`Screen 6 - ANM Identity Review.dc.html`)
Tablet, 834px reference width. One pair at a time; queue position shown
("Pair 1 of 4"). Purpose: let the nurse resolve a probable-duplicate patient
match quickly and confidently — a wrong merge is worse than a slow one.
- **Layout:** two name headers (Existing record / New referral) → a red-
  outlined "name is spelled differently" callout with both spellings side by
  side (only shown when names differ) → a field-by-field comparison table
  (Field / Existing / New); matching fields render as plain rows, any field
  that **disagrees** gets a 1.5px red border, red-tinted background, and a
  header note explaining what to check — so disagreement is the only thing
  that visually stands out. → two large, equal-weight footer buttons: primary
  "Same person — merge", secondary outline "Different people — keep both".
  No third/skip option is presented in this bundle; confirm with the team
  whether a "not sure, ask supervisor" path is needed before build.

### 7. Login (`Screen 7 - Login.dc.html`)
Phone. Intentionally plain, per brief: centered form with phone number field,
4-dot PIN field, a 4-option role grid (ASHA / ANM / MO / Supervisor, single
select, selected option filled in accent), primary "Log in" button, and a
footer line: "Works without signal. You stay logged in on this phone."

## State → label mapping
The event-log state names (source of truth) and the plain-language labels
shown in the UI — the only place these two vocabularies should meet is a
single lookup table in code:

| Log state | Shown as | Family |
|---|---|---|
| Created | Not travelled yet | Fine |
| In transit | On the way | Fine |
| Arrived | Reached the centre | Fine |
| Treated | Doctor has seen her/him | Fine |
| Back referred | Sent back to you | Fine |
| Escalated | Overdue (shown as an overlay on top of the real state, not a replacement — the row keeps its real state label and gains the red pill + bar; when an update arrives the red clears and the row returns to its real state) | Overdue |
| Closed | Care finished | Done |
| Lost | No longer followed | Done |

## Assets
No images or icons beyond system-drawn shapes (circles, checks, crosses) and
one dashed-circle empty-state placeholder. No external assets to source.

## Files in this bundle
- `Design System.dc.html` — full token reference (colors, type, spacing,
  three-shape rule, state table, controls)
- `Screen 1 - ASHA My Referrals.dc.html`
- `Screen 2 - ASHA Create Referral.dc.html`
- `Screen 3 - Referral Detail.dc.html`
- `Screen 4 - Supervisor Dashboard.dc.html`
- `Screen 5 - MO Incoming Referrals.dc.html`
- `Screen 6 - ANM Identity Review.dc.html`
- `Screen 7 - Login.dc.html`
- `UI_DESIGN_BRIEF.md` — the filled-in project design brief (destination
  `docs/UI_DESIGN_BRIEF.md` per the project's handoff process)
