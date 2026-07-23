# The Prompter's Box — Layout Audition

Three full-surface layout prototypes for the booth front's redesign: navigation
to a vertical **Pin Rail** on the right, status to **the Pit** across the bottom,
workspace to **the Deck** on the left/center — built for a window that lives docked
at the right of the monitor.

Each mock renders the entire surface with fake-but-honest booth data (The Kiln
flown in, the Curing Rack holding three firings, the footlights reading
Forge ready · Face warm · Stage LIVE · Foley dark · Kiln ready, Stage load 41%).
They are self-contained HTML — inline CSS, a little vanilla JS, no build step.

## The three variants

- **v1-pin-rail.html** — *The Pin Rail, straight.* A 220px labelled rail full
  height on the right; the five Callboard station plates relocated **whole** into
  the Pit; marquee top-left. The zero-disruption fallback.
- **v2-fly-rail.html** — *The Working Fly Rail + the Light Board.* The rail
  collapses to 68px and flies open to 248px on hover / focus / pin; the five
  engine lines wear their live station lamp **in the rail** (nav×status fusion);
  the Pit is a full-width light board of footlight bulbs, a master fader channel,
  and the blackout lever ⎇, with the marquee as a corner cartouche. The Artisan's
  strongest fit for the docked-window problem.
- **v3-prompt-book.html** — *The Prompt Book (the oppositional read).* The Deck
  becomes a lit prompt-book page (paper ground, ink panels, running head); the
  machinery goes into genuinely dark wings; the rail is a ring-binder whose active
  thumb-tab dog-ears into the page; the Pit is a typed footlight ledger. The most
  literally on-theme — a prompter's box holds a prompt book.

## How to open

Open any file directly in a browser — they work over `file://`, no server needed:

```
file:///…/prompter-box/front/auditions/v2-fly-rail.html
```

Try clicking rail lines (they fly a room in), the blackout lever / evict (the
footlights cool L→R and relight after ~1.2s), and — in V2 — hovering the rail or
hitting the pin. Every variant honours `prefers-reduced-motion`: blackouts snap,
lamps hold steady, and V3 has no pulse at all — LIVE signals by value.

## The blueprint

`DESIGN-SPEC.md` in this folder carries the full Artisan blueprint: the named
regions, the eleven lines and their wings, per-variant behaviour, the Bold Choices
Ledger, and the floors. Read it before judging the mocks — these are the
performance; that is the score.
