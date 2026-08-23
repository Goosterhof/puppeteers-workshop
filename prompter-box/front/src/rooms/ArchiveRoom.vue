<script setup lang="ts">
import {TextInput} from '@script-development/ui-inputs';
import {computed, nextTick, onBeforeUnmount, onMounted, ref, watch} from 'vue';
import CanisterCard from '../components/CanisterCard.vue';
import FilterPills from '../components/FilterPills.vue';
import PinnedRecipeCard from '../components/PinnedRecipeCard.vue';
import StampedMount from '../components/StampedMount.vue';
import type {MountAct} from '../components/StampedMount.vue';
import {age, filterArchive, ROOMS} from '../lib/canisters';
import type {ShelfItem} from '../lib/canisters';
import {canisterRecipe} from '../lib/pins';
import type {PinnedRecipe} from '../lib/pins';
import {archive, loadArchive} from '../stores/archive';
import {castAsLead, facePrompt, leadRes, loadFoleySources, openTab} from '../stores/booth';
import {hangPin, kilnHandoff, loadPins, pins, stageHandoff, takeDownPin} from '../stores/pins';

// The Light Table (2026-08-23) — the room stopped being a wall of prints you
// walk past and became a bench you work at. The print lies on the bench under
// a fixed lamp; the shelf racks up beside it and scrolls PAST the print
// instead of dragging it out of sight. One law rules the whole room:
//
//   R0 — mounting a canister may never scroll the deck.
//
// which is why there is no scrollIntoView on the bench any more. The old call
// was not a bad line of code; it was the layout confessing that the print and
// the shelf shared one scroll container. They no longer do.

const props = withDefaults(defineProps<{active?: boolean}>(), {active: false});

const search = ref('');
const room = ref('');
const kind = ref('');
const mounted = ref<ShelfItem | null>(null);
const acts = ref<MountAct[]>([]);
const root = ref<HTMLElement | null>(null);
const head = ref<HTMLElement | null>(null);
const print = ref<InstanceType<typeof StampedMount> | null>(null);

const items = computed(() => filterArchive(archive.value, {room: room.value, kind: kind.value, search: search.value}));
const filtered = computed(() => Boolean(room.value || kind.value || search.value.trim()));
const key = (it: ShelfItem) => `${it.room}/${it.name}`;

// Where the print sits in the filtered order. It is a ref, not a computed, on
// purpose: when the mounted canister LEAVES the list (binned), the room still
// needs the place it left behind to know what to reach for next.
const lastIndex = ref(-1);
watch([mounted, items], ([m, list]) => {
    if (!m) {
        lastIndex.value = -1;
        return;
    }
    const i = list.findIndex(x => x.room === m.room && x.name === m.name);
    if (i >= 0) lastIndex.value = i;
}, {immediate: true});

// The count line teaches the grammar in the booth's own words — a shelf
// talking, not a key manual. It carries the position readout too, so the eye
// always knows where along the shelf it is.
const countLine = computed(() => {
    if (!items.value.length) {
        return filtered.value
            ? 'No canister answers that description — loosen a filter.'
            : 'The shelves are bare — nothing developed yet. Every Stage take, painting, and score lands here on its own.';
    }
    const mark = filtered.value ? ' — filtered' : '';
    const here = mounted.value ? lastIndex.value + 1 : 0;
    return here > 0
        ? `${here} of ${items.value.length} on the shelf${mark}. Walk them with ← →; Del bins the one on the bench; Esc puts it down.`
        : `${items.value.length} canister${items.value.length === 1 ? '' : 's'} on the shelf${mark}. Take one down to the bench — then ← → walk the shelf and / comes back here.`;
});

// The archive mount is a Print like every fresh take (#00085 detonation 3):
// same paper, same chips — the age stamp sits where Fresh sits.
const mountedSrc = computed(() => mounted.value
    ? ROOMS[mounted.value.room].src + encodeURIComponent(mounted.value.name) : '');
const mountedTitle = computed(() => !mounted.value ? ''
    : mounted.value.meta?.prompt ? `“${mounted.value.meta.prompt}” — ${mounted.value.name}`
    : mounted.value.name);

// The Pinboard (#08) — naming happens here, on the mount, because a pin is
// born from the take you are looking at, never authored from thin air.
const pinning = ref(false);
const pinName = ref('');
const pinError = ref('');

async function confirmPin() {
    if (!mounted.value) return;
    pinError.value = '';
    try {
        await hangPin({
            name: pinName.value,
            room: mounted.value.room,
            source: mounted.value.name,
            recipe: canisterRecipe(mounted.value.meta || {}),
        });
        pinning.value = false;
    } catch (e) {
        pinError.value = (e as Error).message || String(e);
    }
}

function applyPin(pin: PinnedRecipe) {
    const handoff = {name: pin.name, recipe: pin.recipe};
    if (pin.room === 'kiln') {
        kilnHandoff.value = handoff;
        openTab('kiln');
    } else if (pin.room === 'stage') {
        stageHandoff.value = handoff;
        openTab('stage');
    } else if (pin.room === 'face' && typeof pin.recipe.prompt === 'string') {
        facePrompt.value = pin.recipe.prompt;
        openTab('face');
    }
}

async function unpin(pin: PinnedRecipe) {
    pinError.value = '';
    try {
        await takeDownPin(pin.id);
    } catch (e) {
        pinError.value = (e as Error).message || String(e);
    }
}

function buildActs(it: ShelfItem): MountAct[] {
    const rows: MountAct[] = [];
    if (it.meta?.prompt) {
        rows.push({label: 'Copy the cue', run: ctx => {
            navigator.clipboard.writeText(it.meta!.prompt!);
            ctx.relabel('Cue copied');
        }});
    }
    if (it.room === 'stage' && it.kind === 'video') {
        rows.push({label: 'Score it in the foley booth →', run: async () => {
            await loadFoleySources(`stage:${it.name}`);
            openTab('foley');
        }});
    }
    if (it.room === 'stage' && it.kind === 'image') {
        rows.push({label: 'Cast as a lead →', run: async ctx => {
            await castAsLead(it.name, 'stage');
            ctx.relabel('Cast — it is in the footage now');
        }});
    }
    if (it.room === 'face') {
        rows.push({label: 'Send to the stage →', run: async ctx => {
            await castAsLead(it.name);
            const img = ctx.el?.querySelector('img');
            if (img?.naturalWidth) leadRes.value = {w: img.naturalWidth, h: img.naturalHeight};
            openTab('stage');
        }});
    }
    if (Object.keys(canisterRecipe(it.meta || {})).length) {
        rows.push({label: 'Pin this recipe…', run: () => {
            pinName.value = it.meta?.prompt?.slice(0, 60) || it.name;
            pinError.value = '';
            pinning.value = true;
        }});
    }
    return rows;
}

// R0: the print changes, the deck does not move. No scroll call of any kind.
function mountCanister(it: ShelfItem) {
    mounted.value = it;
    acts.value = buildActs(it);
    pinning.value = false;
}

function putDown() {
    mounted.value = null;
    acts.value = [];
    pinning.value = false;
}

// --- the shelf closing its gap -------------------------------------------
// The only new motion in the room, and it belongs to the surface that
// RECEIVES the act: nothing shreds, nothing flies to a bin, the survivors
// simply slide into the space. Off except in the 200ms after a bin, so a
// search keystroke never sets 193 cards moving.
const closing = ref(false);
let closeTimer: ReturnType<typeof setTimeout> | undefined;

// The mount bins the file itself, awaits the reload, and only then emits —
// so by the time we hear it, `items` is already fresh and the victim is gone.
// The successor is therefore the item that has SLID INTO the victim's index:
// down the shelf, toward what has not been looked at yet. At the end of the
// shelf it falls back up one; on a bare shelf the bench simply empties.
function onBinned() {
    const i = lastIndex.value;
    const list = items.value;
    const next = list[i] ?? list[i - 1] ?? null;
    closing.value = true;
    clearTimeout(closeTimer);
    closeTimer = setTimeout(() => {
        closing.value = false;
    }, 200);
    if (next) mountCanister(next);
    else putDown();
}

// --- the keyboard grammar -------------------------------------------------
const reducedMotion = () => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

const inTextField = (t: EventTarget | null): boolean => t instanceof HTMLElement
    && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName));

const cardFor = (it: ShelfItem) => Array.from(root.value?.querySelectorAll<HTMLElement>('.canister') ?? [])
    .find(el => el.dataset.canister === key(it));

// The ONE legal scroll in the room, and only because the bench is sticky: the
// deck moves the shelf, the print stays exactly where it was. `preventScroll`
// is not optional — the browser's default focus scroll is the same class of
// defect as the mount scroll this room deleted.
async function reveal(it: ShelfItem) {
    await nextTick();
    const card = cardFor(it);
    if (!card) return;
    card.focus({preventScroll: true});
    card.scrollIntoView({block: 'nearest', behavior: reducedMotion() ? 'auto' : 'smooth'});
}

function walkTo(index: number) {
    const it = items.value[index];
    if (!it) return;
    mountCanister(it);
    reveal(it);
}

function walk(step: number) {
    const list = items.value;
    if (!list.length) return;
    if (lastIndex.value < 0 || !mounted.value) {
        walkTo(step > 0 ? 0 : list.length - 1);
        return;
    }
    walkTo(Math.min(list.length - 1, Math.max(0, lastIndex.value + step)));
}

const focusSearch = () => root.value?.querySelector<HTMLInputElement>('#arch-search')?.focus();

// One table, one key, one act — no branching ladder to misread.
const ACTS: Record<string, () => void> = {
    ArrowRight: () => walk(1),
    ArrowDown: () => walk(1),
    ArrowLeft: () => walk(-1),
    ArrowUp: () => walk(-1),
    Home: () => walkTo(0),
    End: () => walkTo(items.value.length - 1),
    Delete: () => print.value?.askToBin(),
    Backspace: () => print.value?.askToBin(),
    '/': () => focusSearch(),
};

// Esc is the only key that also fires from inside a text field, where it
// first clears the search box; outside one it puts the print down.
function escapeKey(field: boolean) {
    if (!field) {
        putDown();
        return;
    }
    if (search.value) search.value = '';
}

function onKeydown(e: KeyboardEvent) {
    if (!props.active) return;
    // while the bin's confirm is up the dialog owns the keyboard, Esc included
    if (root.value?.querySelector('dialog[open]')) return;
    const field = inTextField(e.target);
    if (e.key === 'Escape') {
        escapeKey(field);
        return;
    }
    // every other binding is inert while the investor is typing
    if (field) return;
    const act = ACTS[e.key];
    if (!act) return;
    e.preventDefault();
    act();
}

// The bench sticks BELOW the shelf head, whose height changes when the pills
// wrap — so the room measures it rather than guessing a number.
let ruler: ResizeObserver | undefined;
function measureHead() {
    const h = head.value?.offsetHeight;
    if (h) root.value?.style.setProperty('--shelf-head', `${Math.round(h)}px`);
}

onMounted(() => {
    document.addEventListener('keydown', onKeydown);
    if (typeof ResizeObserver === 'undefined' || !head.value) return;
    ruler = new ResizeObserver(measureHead);
    ruler.observe(head.value);
});
onBeforeUnmount(() => {
    document.removeEventListener('keydown', onKeydown);
    ruler?.disconnect();
    clearTimeout(closeTimer);
});

// fresh shelves on entry, same as the old tab hook — and once at first light
watch(() => props.active, a => {
    if (!a) return;
    loadArchive();
    loadPins();
    nextTick(measureHead);
}, {immediate: true});
</script>

<template>
  <div ref="root" class="panel light-table">
    <div ref="head" class="shelf-head">
      <div class="row">
        <div style="flex:2;min-width:220px">
          <label class="field" for="arch-search">Search the shelves — filename, prompt slug, seed</label>
          <TextInput id="arch-search" v-model="search" placeholder="seed7, crier, flask…" />
        </div>
        <div>
          <label class="field">Room</label>
          <FilterPills
            v-model="room"
            :options="[{value: '', label: 'All'}, {value: 'stage', label: 'Stage'},
                       {value: 'face', label: 'Face Shop'}, {value: 'foley', label: 'Foley'}]"
          />
        </div>
        <div>
          <label class="field">Kind</label>
          <FilterPills
            v-model="kind"
            :options="[{value: '', label: 'All'}, {value: 'video', label: 'Reels'},
                       {value: 'image', label: 'Stills'}, {value: 'audio', label: 'Audio'}]"
          />
        </div>
      </div>
      <p id="arch-count" class="note">{{ countLine }}</p>
    </div>

    <div v-if="pins.length" id="pinboard">
      <p class="pinboard-head">The Pinboard — named formulas, promoted from proven takes</p>
      <div class="pinboard-grid">
        <PinnedRecipeCard v-for="p in pins" :key="p.id" :pin="p" @apply="applyPin" @unpin="unpin" />
      </div>
    </div>
    <p v-show="pinError && !pinning" class="error">{{ pinError }}</p>

    <div class="light-table-split">
      <!-- THE BENCH — sticky under the shelf head, in its own pool of lamplight -->
      <div id="arch-view" class="bench bench-narrow">
        <StampedMount
          v-if="mounted"
          :key="`${mounted.room}/${mounted.name}`" ref="print"
          :room="mounted.room" :url="mountedSrc" :kind="mounted.kind || 'video'"
          :title="mountedTitle" :meta="mounted.meta" :stamp="age(mounted.mtime)" :acts="acts"
          @binned="onBinned"
        />
        <p v-else class="bench-bare">The bench is bare. Take a canister down off the shelf — it stays under the lamp while you walk the rest.</p>
        <div v-if="mounted && pinning" class="pin-naming">
          <label class="field" for="pin-name">Name the formula — what will you ask for again?</label>
          <div class="row" style="align-items:flex-end">
            <div style="flex:2;min-width:220px"><TextInput id="pin-name" v-model="pinName" placeholder="Spoked Vehicle" /></div>
            <div><button class="fire" style="margin-top:0" @click="confirmPin">Hang it on the board</button></div>
            <div><button class="act pin-cancel" @click="pinning = false">Cancel</button></div>
          </div>
          <p v-show="pinError" class="error">{{ pinError }}</p>
        </div>
      </div>

      <!-- THE SHELF — the thumbrow class rides along like the old markup; its
           2px transparent border and .88 opacity on the folio are the look -->
      <TransitionGroup
        id="arch-grid" tag="div" class="shelf thumbrow"
        :move-class="closing ? 'shelf-close' : 'shelf-still'"
        enter-active-class="shelf-still" leave-active-class="shelf-still"
      >
        <CanisterCard
          v-for="it in items" :key="`${it.room}/${it.name}`" :item="it"
          :on-bench="mounted ? it.room === mounted.room && it.name === mounted.name : false"
          @mount="mountCanister"
        />
      </TransitionGroup>
    </div>
  </div>
</template>

<style>
/* ===== The Light Table ===== the shelf head rules the page, the bench stays
   under the lamp, the shelf scrolls past it. */
.light-table { --shelf-head: 132px; }

/* R1 — search and both pill groups are reachable at any scroll depth. The
   head pins ABOVE the deck's own top padding: the shelf scrolls through that
   gutter, and a head pinned at 0 would leave a 26px sliver of moving cards
   riding over it. Nothing changes at rest. */
.shelf-head {
  position: sticky; top: calc(-1 * var(--deck-pad-top, 0px)); z-index: 2;
  background: var(--page); padding-bottom: 12px;
  border-bottom: 1px solid var(--ink-hair);
}

/* Column math at a 1400 deck: the panel's own 22px padding leaves 1354.
   The bench column is 760 + its 2×16 of lamplight = 792, so the print sits at
   its TRUE 760 and is never scaled to make the shelf wider (the audit's
   second trip-wire). Shelf = 1354 − 792 − 24 = 538 → four cards at 125px. */
.light-table-split {
  display: grid; grid-template-columns: 792px minmax(0, 1fr);
  column-gap: 24px; align-items: start; margin-top: 16px;
}

/* the bench: sticky, never a nested scroll container (no overflow, no height
   plumbing) — and lit. The wash is VALUE, never motion: the sticky column has
   to read as a lit surface, not as a div that failed to scroll. */
.bench {
  /* flush under the pinned head — the head reaches up through the deck's top
     gutter, so the bench's own offset has to come back down by the same
     amount or a sliver of moving cards wedges itself in between */
  position: sticky; top: calc(var(--shelf-head) - var(--deck-pad-top, 0px));
  align-self: start; z-index: 1;
  /* keeps the sticky box shorter than the scrollport so it sticks to the TOP
     rather than to the bottom edge; the content is sized to fit inside it */
  max-height: calc(100vh - var(--shelf-head) - 24px);
  display: flex; flex-direction: column; gap: 14px;
  padding: 14px 16px 18px; border-radius: 2px;
  background: linear-gradient(178deg, var(--page) 0%, var(--page) 40%, color-mix(in srgb, var(--ink) 6%, var(--page)) 100%);
}
/* the print is never scaled to fit the column (it is 760 because .mount is
   760) — but on a short window the lamp lowers rather than the acts row
   falling off the bottom of the screen */
.bench .mount-frame img, .bench .mount-frame video {
  /* 300 = the head's own offset in the deck + the print's body + the bench's
     lamplight padding + the footlight ledger. Measured, not guessed: at a
     1000px window the whole print INCLUDING its acts row has to be reachable
     without scrolling, or the bench is not a bench. */
  max-height: min(62vh, calc(100vh - var(--shelf-head) - 300px));
}
.bench-bare {
  font-size: 12.5px; font-style: italic; color: var(--ink-soft);
  line-height: 1.6; padding: 22px 4px; max-width: 46ch;
}

/* one ink hairline between the bench and the shelf — drawn in the gutter so
   it costs the shelf no width */
.shelf { position: relative; }
.shelf::before {
  content: ''; position: absolute; left: -12px; top: 0; bottom: 0; width: 1px;
  background: var(--ink-hair);
}
#arch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(124px, 1fr)); gap: 12px; }

/* the gap closing after a bin — 150ms, and the reduced-motion preflight
   gates it to nothing like every other transition in the booth */
.shelf-close { transition: transform 150ms ease; }
.shelf-still { transition: none; }

#pinboard { margin-top: 18px; }
.pinboard-head {
  font: 11px var(--display); letter-spacing: .2em; text-transform: uppercase;
  color: var(--dim); margin-bottom: 10px;
}
.pinboard-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; }
.pin-naming { width: 100%; max-width: 760px; }
.pin-naming .act.pin-cancel {
  background: none; border: 1px solid var(--drape-edge); color: var(--dim);
  font: 11px var(--display); letter-spacing: .16em; text-transform: uppercase;
  padding: 11px 16px; cursor: pointer; border-radius: 2px;
}
.pin-naming .act.pin-cancel:hover { border-color: var(--lamp-dim); color: var(--lamp); }

/* ===== Below 1180 the split folds: the bench goes on top, still sticky, and
   the print turns landscape so it costs at most 40vh of the window. The
   StampedMount's own markup is untouched — this is a scope the ROOM applies
   (R2). ===== */
@media (max-width: 1180px) {
  .light-table-split { grid-template-columns: minmax(0, 1fr); row-gap: 18px; }
  .shelf::before { display: none; }
  /* the shelf has the whole page now — five cards at ~158, not eight at 100 */
  #arch-grid { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
  .canister { contain-intrinsic-size: 0 148px; }
  .bench { max-height: calc(100vh - var(--shelf-head) - 16px); padding: 12px 12px 14px; }
  .bench-narrow .mount { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); }
  .bench-narrow .mount-frame { align-items: center; }
  .bench-narrow .mount-frame img, .bench-narrow .mount-frame video { max-height: 40vh; }
  .bench-narrow .mount-body { padding: 12px 14px 14px; }
  .bench-narrow .mount-title { font-size: 12.5px; }
}
</style>
