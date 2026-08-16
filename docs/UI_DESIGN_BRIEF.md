# UI design brief

**Destination:** `docs/UI_DESIGN_BRIEF.md`

**How to use this:** fill in what you have opinions about, delete or write
"Claude decides" next to the rest. Anything left as "Claude decides" is Claude
Code's call under §8 of the handoff. An empty brief is fine — it just means the
design is Claude Code's to choose. A half-filled brief is better than a
conversation about it every session.

**Before Phase 4, tell Claude Code whether this file is filled in or not.**

---

## 1. Reference images or links

_Paste screenshots into `docs/design/` and list them here, or link to any app
whose look you want. "Like the Google Pay list screen" is a useful instruction._

-
-

## 2. Overall feeling

_Pick one, or write your own:_

- [ ] Clinical and plain — white, high contrast, no decoration. Looks like a tool.
- [ ] Warm and simple — soft colours, big friendly type. Looks approachable.
- [ ] Government-service style — familiar to Indian public-health users.
- [ ] Claude decides.

## 3. Colour

- Primary colour: _(hex, or "Claude decides")_
- Are there colours to avoid? _(e.g. red reserved only for overdue)_
- State colours — one per referral state, or one for "fine / overdue / done"?

## 4. Type

- Font preference: _(or "Claude decides")_
- Any need for Devanagari or Tamil glyphs later? _(scope says English only —
  confirm)_

## 5. Screens you know you want

_List the screens you already have in mind. Anything not listed, Claude Code
proposes and you approve — screen structure is a user decision under §2 of the
handoff._

**ASHA (phone):**
- Create referral
- My referrals list
-

**ANM:**
- Identity review queue
-

**MO (tablet or desktop):**
-

**Supervisor (desktop):**
- Live escalation dashboard
-

## 6. The offline indicator

This is the one piece of interface the whole architecture exists to justify, so
be deliberate. The user must always know: am I online, how many updates are
waiting, when did I last sync.

- Where does it live? _(top bar / bottom bar / floating / Claude decides)_
- What does it say when offline with work pending?
- What does it say the moment everything has synced?

## 7. The escalation moment

A referral breaching its deadline and appearing live on the supervisor dashboard
without a page refresh is the twenty seconds the panel will remember. Design for
it deliberately.

- Should it animate in, or just appear?
- Sound? _(usually no — reviews are in a quiet room)_
- How obvious should "overdue by 2 days" be versus "overdue by 2 hours"?

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
