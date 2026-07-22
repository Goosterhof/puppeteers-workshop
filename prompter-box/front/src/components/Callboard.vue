<script setup lang="ts">
import {ref} from 'vue';
import {useStatusHeartbeat} from '../composables/useStatusHeartbeat';
import type {LampState, StationName} from '../lib/stationState';

// The five stations, in wiring order — the ledger reads them L→R like a
// margin note. Same identities the plates carried; the Prompt Book (#00064)
// just types them along the stage lip instead of framing them.
const PLATES: {id: StationName; pos: string; cue: string}[] = [
    {id: 'forge', pos: 'Forge', cue: 'Promptsmith · Ollama'},
    {id: 'face', pos: 'Face', cue: 'ComfyUI'},
    {id: 'stage', pos: 'Stage', cue: 'Wan2GP'},
    {id: 'foley', pos: 'Foley', cue: 'MMAudio'},
    {id: 'kiln', pos: 'Kiln', cue: 'Hunyuan3D · Klein'},
];

const {board, poll, evict} = useStatusHeartbeat();
const blackout = ref(false);
const evictLabel = ref('clear the boards');

// The Face Shop reads "warm" on standby (the model is resident, not idle-cold)
// and a live lamp shouts — same word choices as the plates always made.
const stateWord = (id: StationName, state: LampState) =>
    state === 'standby' && id === 'face' ? 'warm' : state === 'live' ? 'LIVE' : state;

// The blackout forces every lamp's SHOWN state dark; the heartbeat's truth
// returns with the relight poll. V3 is the quietest variant: a value swap,
// no cascade, no pulse — the word LIVE losing its filament IS the event.
const shown = (id: StationName): LampState => (blackout.value ? 'dark' : board.stations[id].state);

// Only the stations that hold something get a margin note — live (what is
// rendering) and held (who refuses cues). ready/warm speak for themselves.
const readFor = (id: StationName): string => {
    const st = shown(id);
    return (st === 'live' || st === 'held') ? board.stations[id].read : '';
};

async function clearTheBoards() {
    blackout.value = true; // every lamp cools by value — the master switch thrown
    try {
        const evicted = await evict();
        evictLabel.value = evicted.length
            ? `${evicted.length} voice${evicted.length === 1 ? '' : 's'} left the boards`
            : 'the boards were already clear';
    } catch {
        evictLabel.value = 'the booth is not answering';
    }
    setTimeout(() => {
        evictLabel.value = 'clear the boards';
    }, 2600);
    setTimeout(() => {
        blackout.value = false;
        poll();
    }, 1200);
}
</script>

<template>
  <div
    id="callboard" class="pit" :class="{cold: board.cold, blackout}"
    role="status" aria-label="The footlight ledger — who holds the boards"
  >
    <span
      v-for="p in PLATES" :key="p.id"
      class="ledger-item" :class="`is-${shown(p.id)}`" :data-station="p.id" :title="p.cue"
    >
      <i class="cue-lamp" :class="shown(p.id)"></i>{{ p.pos }}&nbsp;<span class="st">{{ stateWord(p.id, shown(p.id)) }}</span>
      <span v-if="readFor(p.id)" class="rd">· {{ readFor(p.id) }}</span>
    </span>
    <span class="ledger-sep">·</span>
    <span id="occ-read" class="ledger-read">Stage load {{ Math.round(board.occ.pct) }}% · <b>{{ board.occ.read }}</b></span>
    <button id="evict" class="evict-typed" title="Unload every LLM from the GPU" @click="clearTheBoards">{{ evictLabel }}</button>
  </div>
</template>

<style>
/* ===== The Pit: the typed footlight ledger (#00064 Phase C).
   No pulse — LIVE signals by value in --filament, the quietest organ the
   booth has ever had. The prompter writes the board state in the margin. ===== */
.pit {
  grid-area: pit; background: var(--booth); border-top: 1px solid var(--drape-edge);
  display: flex; align-items: center; flex-wrap: wrap; gap: 2px 4px;
  padding: 14px 20px; font: 13px var(--typed); color: var(--dim);
}
.ledger-item { display: inline-flex; align-items: center; white-space: nowrap; }
.cue-lamp {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  border: 1px solid var(--lamp-dim); background: var(--stage-off); margin: 0 6px 0 14px;
}
.cue-lamp.ready   { background: var(--go-green); border-color: var(--go-green); }
.cue-lamp.standby { background: var(--lamp); border-color: var(--lamp); }
.cue-lamp.held    { background: var(--cue-red); border-color: var(--cue-red); }
.cue-lamp.live    { background: var(--filament); border-color: var(--lamp); box-shadow: 0 0 5px rgba(255,210,122,.7); } /* value, never motion */
.cue-lamp.dark    { background: var(--stage-dead); border-color: var(--plate-edge); }
.ledger-item .st { color: var(--dim); }
.ledger-item.is-ready .st   { color: var(--go-green); }
.ledger-item.is-standby .st { color: var(--lamp); }
.ledger-item.is-held .st    { color: var(--cue-red); }
.ledger-item.is-live .st    { color: var(--filament); font-weight: 700; letter-spacing: .06em; }
.ledger-item .rd { color: var(--dim); margin-left: 6px; font-style: italic; max-width: 260px; overflow: hidden; text-overflow: ellipsis; }
.ledger-sep { color: var(--drape-edge); margin: 0 2px 0 14px; }
.ledger-read { margin-left: 20px; color: var(--dim); }
.ledger-read b { color: var(--paper); font-weight: 400; }
.evict-typed {
  margin-left: auto; background: none; border: 1px solid var(--drape-edge); color: var(--dim);
  font: 11px var(--typed); letter-spacing: .04em; padding: 7px 13px; cursor: pointer; border-radius: 2px;
}
.evict-typed:hover { border-color: var(--cue-red); color: var(--cue-red); }
.evict-typed:focus-visible { outline: 2px solid var(--lamp-dim); }

@media (max-width: 1000px) {
  .pit { gap: 2px; padding: 12px 14px; }
  .ledger-read { margin-left: 14px; }
  .ledger-item .rd { display: none; } /* the margin notes yield first in a narrow booth */
}
</style>
