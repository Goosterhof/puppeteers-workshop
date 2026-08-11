<script setup lang="ts">
import {computed} from 'vue';
import Callboard from './components/Callboard.vue';
import {slugify} from './lib/slugify';
import ArchiveRoom from './rooms/ArchiveRoom.vue';
import FaceRoom from './rooms/FaceRoom.vue';
import FoleyRoom from './rooms/FoleyRoom.vue';
import ForgeRoom from './rooms/ForgeRoom.vue';
import HouseFaceRoom from './rooms/HouseFaceRoom.vue';
import HouseStageRoom from './rooms/HouseStageRoom.vue';
import KilnRoom from './rooms/KilnRoom.vue';
import NightShiftRoom from './rooms/NightShiftRoom.vue';
import RackRoom from './rooms/RackRoom.vue';
import ShelfRoom from './rooms/ShelfRoom.vue';
import StageRoom from './rooms/StageRoom.vue';
import {activeTab as active, loadFootage} from './stores/booth';

// one footage fetch feeds the three thumb rows, like the old boot-time load
loadFootage().catch(() => {});

// The eleven rooms, in the old front's tab order. Plain reactive tab state —
// no router; the booth never had deep links (#00063 §1A).
const TABS = [
    {id: 'forge', label: 'Forge', room: ForgeRoom},
    {id: 'kiln', label: 'The Kiln', room: KilnRoom},
    {id: 'rack', label: 'The Curing Rack', room: RackRoom},
    {id: 'shelf', label: 'The Prop Shelf', room: ShelfRoom},
    {id: 'nightshift', label: 'The Night Shift', room: NightShiftRoom},
    {id: 'stage', label: 'The Stage', room: StageRoom},
    {id: 'face', label: 'Face Shop', room: FaceRoom},
    {id: 'foley', label: 'Foley Booth', room: FoleyRoom},
    {id: 'archive', label: 'The Canisters', room: ArchiveRoom},
    {id: 'house-stage', label: 'Stage UI', room: HouseStageRoom},
    {id: 'house-face', label: 'Face Shop UI', room: HouseFaceRoom},
];

// The Prompt Book (#00064): the eleven lines hang in four wings down the
// stage-right binder. Grouping is production anatomy, not cosmetics — the
// four authored stations, the fabrication pipeline, the archive, and the
// raw passthrough consoles under the deck.
const WINGS: {head: string; ids: string[]}[] = [
    {head: 'Performance', ids: ['forge', 'face', 'stage', 'foley']},
    {head: 'The Kiln Wing', ids: ['kiln', 'rack', 'shelf', 'nightshift']},
    {head: 'The Vault', ids: ['archive']},
    {head: 'Understage', ids: ['house-stage', 'house-face']},
];
const line = (id: string) => TABS.find(t => t.id === id)!;
const activeLabel = computed(() => TABS.find(t => t.id === active.value)?.label ?? '');
const wingId = (head: string) => `wing-${slugify(head)}`;

// The binder is a real ARIA tablist, so it owes the whole pattern (enhancement
// report #00009, P2-6): panels linked back to their tabs, ONE tab in the tab
// order at a time, and the arrows walking the rail once focus is on it. The
// wings are presentational — a tablist may only own tabs, so the wing head
// hands its name to each thumb-tab through aria-describedby instead of
// wrapping them in a group the pattern forbids.
const RAIL = WINGS.flatMap(w => w.ids); // rail order, top to bottom — what the arrows walk
const thumbTabs: Record<string, HTMLButtonElement> = {};
const registerTab = (id: string, el: unknown) => {
    if (el instanceof HTMLButtonElement) thumbTabs[id] = el;
};

// Automatic activation: the rail's panels are already mounted and cost nothing
// to show, so focus and selection travel together — no second keystroke to
// open the page the reader just arrived at.
const STEP: Record<string, (i: number) => number> = {
    ArrowDown: i => (i + 1) % RAIL.length,
    ArrowRight: i => (i + 1) % RAIL.length,
    ArrowUp: i => (i + RAIL.length - 1) % RAIL.length,
    ArrowLeft: i => (i + RAIL.length - 1) % RAIL.length,
    Home: () => 0,
    End: () => RAIL.length - 1,
};
function turnThePage(event: KeyboardEvent, from: string) {
    const step = STEP[event.key];
    const here = RAIL.indexOf(from);
    if (!step || here < 0) return;
    event.preventDefault();
    const id = RAIL[step(here)]!;
    active.value = id;
    thumbTabs[id]?.focus();
}
</script>

<template>
  <div class="booth">
    <main class="deck folio-page">
      <div class="deck-inner">
        <div class="runhead">
          <h1 class="title">The Prompter's Box<small>the booth that feeds the lines</small></h1>
          <div class="folio">open to <b>{{ activeLabel }}</b></div>
        </div>

        <section
          v-for="t in TABS" v-show="active === t.id" :id="`panel-${t.id}`" :key="t.id"
          role="tabpanel" :aria-labelledby="`tab-${t.id}`"
        >
          <component :is="t.room" :active="active === t.id" />
        </section>
      </div>
    </main>

    <nav
      class="rail" role="tablist" aria-orientation="vertical"
      aria-label="The ring-binder — thumb-tabs down the stage-right wing"
    >
      <div v-for="w in WINGS" :key="w.head" class="wing" role="presentation">
        <div :id="wingId(w.head)" class="wing-head" role="presentation">{{ w.head }}</div>
        <button
          v-for="id in w.ids" :id="`tab-${id}`" :key="id" :ref="el => registerTab(id, el)"
          role="tab" class="tab"
          :aria-selected="active === id" :aria-controls="`panel-${id}`"
          :aria-describedby="wingId(w.head)" :tabindex="active === id ? 0 : -1"
          :data-tab="id"
          @click="active = id" @keydown="turnThePage($event, id)"
        >{{ line(id).label }}</button>
      </div>
    </nav>

    <Callboard />
  </div>
</template>

<style>
/* ===== The Prompt Book shell (#00064 Phase B): lit folio deck, dark
   binder-wing right, typed footlight ledger bottom ===== */
.booth {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 176px;
  grid-template-rows: minmax(0, 1fr) auto;
  grid-template-areas:
    "deck rail"
    "pit  rail";
  height: 100%;
}

/* ---- The Deck: the lit prompt-book page (surface from .folio-page) ---- */
.deck {
  grid-area: deck; position: relative; z-index: 1;
  overflow: auto; padding: 26px 34px 40px;
}
.deck-inner { max-width: 1400px; margin: 0 auto; }

/* the Marquee as a running head on the page */
.runhead {
  display: flex; align-items: baseline; justify-content: space-between; gap: 20px;
  border-bottom: 2px solid var(--ink); padding-bottom: 10px; margin-bottom: 26px;
}
.runhead .title { font: 500 15px var(--display); letter-spacing: .28em; text-transform: uppercase; color: var(--ink); }
.runhead .title small { font: 400 10px var(--typed); letter-spacing: .12em; color: var(--ink-soft); text-transform: none; margin-left: 12px; }
.runhead .folio { font: 400 11px var(--typed); letter-spacing: .1em; color: var(--ink-soft); white-space: nowrap; }
.runhead .folio b { color: var(--ink); font-weight: 700; }

/* ---- The binder-wing (right): ring-binder thumb-tabs ---- */
.rail {
  /* overflow stays visible — a scroll container would clip the dog-ear jut;
     eleven lines + four wing heads fit ~560px and the booth window is taller */
  grid-area: rail; position: relative; z-index: 2; overflow: visible;
  background: var(--booth); border-left: 1px solid var(--drape-edge);
  padding: 14px 0 20px 0;
}
.wing-head { font: 500 10px var(--display); letter-spacing: .26em; text-transform: uppercase; color: var(--lamp-dim); padding: 15px 16px 7px; white-space: nowrap; }
.rail .tab {
  display: block; width: 100%; text-align: left; cursor: pointer;
  background: var(--drape); border: 1px solid var(--drape-edge); border-right: none;
  color: var(--dim); font: 400 12.5px var(--display); letter-spacing: .14em; text-transform: uppercase;
  padding: 11px 14px; margin: 5px 0; border-radius: 4px 0 0 4px; position: relative;
  transition: background .14s ease, color .14s ease, box-shadow .14s ease;
}
.rail .tab:hover { color: var(--paper); background: var(--drape-edge); }
.rail .tab:focus-visible { outline: 2px solid var(--lamp-dim); outline-offset: -2px; }
/* the dog-ear: the active binder tab juts ~12px INTO the page, paper-clad to
   read as part of the open folio (a static jut — reduced motion never sees it move) */
.rail .tab[aria-selected="true"] {
  background: var(--paper); color: var(--ink); border-color: var(--paper);
  font-weight: 600; margin-left: -12px; padding-left: 26px; z-index: 3;
  box-shadow: -2px 0 0 var(--ink);
}
/* the dog-ear takes the heat (chaos #00109 D1): while a take runs, the booth
   must not look idle. The signal it replaces was a page-wide amber wash on
   <body> — struck, because the deck, the rail and the pit tile every pixel of
   the body opaquely and no eye ever reached it. The mutex is a global fact
   (one performance at a time), so the heat rides the one object that crosses
   from the dark booth into the lit page. Value, never motion: the thumb-tab's
   paper warms as if the lamp were turned up, and the ink hairline splits on a
   filament seam. The seam is FRAMED in ink on purpose — --filament reads 12:1
   against the booth but 1.15:1 against cream, so unframed on the page it would
   repeat the original sin and paint where no eye can reach. */
body.take-running .rail .tab[aria-selected="true"] {
  background: color-mix(in srgb, var(--filament) 22%, var(--paper));
  border-color: color-mix(in srgb, var(--filament) 22%, var(--paper));
  box-shadow: -2px 0 0 var(--ink), -7px 0 0 var(--filament), -9px 0 0 var(--ink);
}

/* ===== Responsive — the right-docked window is the design case ===== */
@media (max-width: 1280px) {
  .deck { padding: 22px 24px 36px; }
  .booth { grid-template-columns: minmax(0, 1fr) 164px; }
}
@media (max-width: 1000px) {
  .booth { grid-template-columns: minmax(0, 1fr) 150px; }
  .rail .tab { font-size: 11.5px; padding: 10px 12px; letter-spacing: .1em; }
}
</style>
