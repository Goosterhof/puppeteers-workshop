# Design Spec — The Prompter's Box: Right-Rail, Bottom-Pit Booth

*The Artisan's blueprint for the layout redesign audition (2026-07-22). The investor's
fixed constraint: navigation → vertical rail RIGHT, status → bar BOTTOM, workspace →
LEFT/CENTER — designed for a window that lives at the right of the monitor.*

## The regions, named

| Region | Domain name | What it is |
|---|---|---|
| Workspace (left/center) | **The Deck** | The stage floor where the called room performs. One width, every scene. |
| Vertical nav (right) | **The Pin Rail** | The vertical run of linesets down the stage-right wing; pull a line to fly a room onto the deck. Each room hangs on a **line**; the active line is **flown in**. |
| Status bar (bottom) | **The Pit** | The band across the stage lip: the **footlights** (five station lamps), the **dimmer board** (Stage-load fader), the **blackout lever** (evict). |
| Title | **The Marquee** | Placement varies by variant; V2 collapses it to a cartouche at the rail∩pit corner — where a real prompter's box sits. |

## The eleven lines, grouped into wings (shared across all variants)

- **PERFORMANCE** — Forge · Face Shop · The Stage · Foley Booth
- **THE KILN WING** — The Kiln · The Curing Rack · The Prop Shelf · The Night Shift
- **THE VAULT** — The Canisters
- **UNDERSTAGE** — Stage UI · Face Shop UI

## The variants

- **V1 — The Pin Rail, straight.** 220px labeled rail (full height), Pit spans the deck only
  (~88px) with the five station plates relocated WHOLE (full lamp/eye/state/read anatomy,
  L→R blackout cascade verbatim), marquee top-left, deck ≤1400px. ≤1280: rail 188px, Pit
  wraps. ≤900: rail → 44px lamp-spine, Pit scrolls.
- **V2 — The Working Fly Rail + the Light Board.** Collapsing rail 68px ↔ 248px
  (hover/focus/pin, localStorage), engine rooms wear their LIVE station lamp IN the rail
  (nav⨯status fusion — one heartbeat, two mounts). Pit spans FULL width: footlight bulbs
  (30px, brass bezel), master fader as a light-board channel, blackout lever ⎇. Marquee
  cartouche at rail∩pit. Deck ≤1440px. Blackout = L→R cool along the lip; the lever's
  actor is implied, never drawn.
- **V3 — The Prompt Book (oppositional).** The deck becomes the lit prompt-book page
  (--paper ground, ink panels, running head); the machinery goes into genuinely dark
  wings. Rail = ring-binder thumb-tabs (~176px), the active tab juts ~12px INTO the page.
  Pit = typed footlight ledger ("· Forge ready · Face warm · Stage LIVE ·" in Courier
  Prime, brass cue-lamps, no pulse — LIVE signals by value in --filament). Quietest
  variant under reduced motion by construction.

## Bold Choices Ledger (abridged)

1. Augment the Callboard into the Pit — never demote it to a status strip.
2. The rail is a fly rail, not a menu — wings, not links.
3. Nav⨯status fusion via shared station lamps (V2) — the rail is ambiently alive.
4. The blackout cools along the lip; no lever-arm is ever drawn.
5. V3 lights the deck and darkens the wings — opposition presented full-strength.
6. The active binder tab overlaps the page edge (V3) — the page is dog-eared to the open scene.
7. The marquee sits front-stage-right (V2) — the identity plate in its architectural home.

## Floors

prefers-reduced-motion floor mandatory in every variant (instant blackout, steady lamps,
static juts; V2's rail collapse authored as a gated CSS transition, never a JS loop).
One-width deck surface-wide. No new dependencies, no router, no per-tab special-casing.
No glassmorphism, no pills, no bounce, no drop-shadow elevation — the amber radial wash
is the only lift a gaslit backstage allows.

## The Artisan's read

V2 is the strongest fit for the stated problem (the collapsing rail converts the narrow
right-docked window into an advantage; the fusion is the one new capability the move
makes possible). V1 is the zero-disruption fallback. V3 is the seduction-or-rejection
card — and the most literally on-theme, because a prompter's box holds a prompt book.
