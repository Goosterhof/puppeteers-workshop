<script setup>
import {ref} from 'vue';
import {useStatusHeartbeat} from '../composables/useStatusHeartbeat.js';

// The five station plates, in wiring order — the blackout cools them L→R.
const PLATES = [
    {id: 'forge', pos: 'Forge', cue: 'Promptsmith · Ollama'},
    {id: 'face', pos: 'Face Shop', cue: 'ComfyUI'},
    {id: 'stage', pos: 'Stage', cue: 'Wan2GP'},
    {id: 'foley', pos: 'Foley', cue: 'MMAudio'},
    {id: 'kiln', pos: 'Kiln', cue: 'Hunyuan3D · Klein'},
];

const {board, poll, evict} = useStatusHeartbeat();
const blackout = ref(false);
const evictLabel = ref('Clear the boards');

// The Face Shop reads "warm" on standby (the model is resident, not idle-cold)
// and a live lamp shouts — same word choices as the single-file front.
const stateWord = (id, state) =>
    state === 'standby' && id === 'face' ? 'warm' : state === 'live' ? 'LIVE' : state;

async function clearTheBoards() {
    blackout.value = true; // lamps cool to dark L→R — the master switch thrown
    try {
        const evicted = await evict();
        evictLabel.value = evicted.length
            ? `${evicted.length} voice${evicted.length === 1 ? '' : 's'} left the boards`
            : 'The boards were already clear';
    } catch {
        evictLabel.value = 'The booth is not answering';
    }
    setTimeout(() => {
        evictLabel.value = 'Clear the boards';
    }, 2600);
    setTimeout(() => {
        blackout.value = false;
        poll();
    }, 1200);
}
</script>

<template>
  <div
    id="callboard" class="callboard" :class="{cold: board.cold, blackout}"
    role="status" aria-label="The call board — who holds the stage"
  >
    <div
      v-for="p in PLATES" :key="p.id"
      class="station" :class="board.stations[p.id].state" :data-station="p.id"
    >
      <i class="eye"></i><b class="pos">{{ p.pos }}</b>
      <span class="cue">{{ p.cue }}</span>
      <span class="state">{{ stateWord(p.id, board.stations[p.id].state) }}</span>
      <span class="read">{{ board.stations[p.id].read }}</span>
    </div>
    <div class="dimmer">
      <span class="occ-label">Stage load</span>
      <div class="track"><i id="occ-fill" :style="{width: `${board.occ.pct}%`}"></i></div>
      <span id="occ-read" class="occ-read">{{ board.occ.read }}</span>
    </div>
    <button id="evict" title="Unload every LLM from the GPU" @click="clearTheBoards">{{ evictLabel }}</button>
  </div>
</template>

<style>
.callboard {
  display: flex; flex-wrap: wrap; align-items: stretch; gap: 12px;
  padding: 16px 20px; margin: 0 -20px 6px;
  background: var(--drape); border-bottom: 1px solid var(--drape-edge);
}
.station {
  flex: 1 1 150px; min-width: 140px; display: grid;
  grid-template-columns: auto 1fr; gap: 2px 10px; align-items: center;
  background: var(--plate-face); border: 1px solid var(--plate-edge); border-radius: 3px;
  padding: 12px 14px;
}
.station .eye {
  grid-row: 1 / 5; width: 26px; height: 26px; border-radius: 50%;
  background: var(--stage-off); box-shadow: inset 0 1px 3px rgba(0,0,0,.7);
  transition: background .42s ease, box-shadow .42s ease;
}
.station .pos { font: 500 13px var(--display); letter-spacing: .2em; text-transform: uppercase; color: var(--dim); grid-column: 2; }
.station .cue { font-size: 10px; letter-spacing: .1em; color: var(--dim); grid-column: 2; }
.station .state { font: 11px var(--display); letter-spacing: .18em; text-transform: uppercase; grid-column: 2; color: var(--dim); }
.station .read { font: 10px var(--typed); color: var(--dim); grid-column: 2; opacity: .8; min-height: 1em; }
.station.ready   .eye { background: var(--go-green); box-shadow: 0 0 8px rgba(125,161,107,.6); }
.station.ready   .state { color: var(--go-green); }
.station.standby .eye { background: var(--lamp-dim); box-shadow: 0 0 6px rgba(138,106,46,.5); }
.station.standby .state { color: var(--lamp); }
.station.held    .eye { background: var(--cue-red); box-shadow: 0 0 8px rgba(194,84,58,.6); }
.station.held    .state { color: var(--cue-red); }
.station.live { background: #241a10; border-color: var(--lamp-dim); box-shadow: 0 0 22px rgba(232,176,74,.22); }
.station.live .eye {
  background: radial-gradient(circle at 40% 35%, var(--filament), var(--lamp) 70%);
  box-shadow: 0 0 14px rgba(232,176,74,.9); animation: eye-pulse 1.4s ease-in-out infinite;
}
.station.live .state { color: var(--filament); font-weight: 600; }
@keyframes eye-pulse { 50% { opacity: .5; } }
.callboard.cold .station .eye { background: var(--stage-dead); box-shadow: inset 0 1px 3px rgba(0,0,0,.7); animation: none; }
/* the blackout — lamps cool L→R like killing the work lights */
.callboard.blackout .station .eye {
  background: var(--stage-off) !important;
  box-shadow: inset 0 1px 3px rgba(0,0,0,.7) !important; animation: none !important;
}
.callboard.blackout .station:nth-child(2) .eye { transition-delay: .08s; }
.callboard.blackout .station:nth-child(3) .eye { transition-delay: .16s; }
.callboard.blackout .station:nth-child(4) .eye { transition-delay: .24s; }
.callboard.blackout .station:nth-child(5) .eye { transition-delay: .32s; }  /* the Kiln joins the L→R cool */
.dimmer { flex: 1 1 180px; display: flex; flex-direction: column; justify-content: center; gap: 5px; }
.dimmer .occ-label { font: 10px var(--display); letter-spacing: .2em; text-transform: uppercase; color: var(--dim); }
.dimmer .track { height: 8px; background: var(--meter-well); border-radius: 4px; overflow: hidden; }
.dimmer .track i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, var(--lamp-dim), var(--lamp)); transition: width .4s ease; }
.dimmer .occ-read { font: 11px var(--typed); color: var(--dim); }
#evict {
  align-self: center; background: none; border: 1px solid var(--drape-edge); color: var(--dim);
  font: 11px var(--display); letter-spacing: .18em; text-transform: uppercase;
  padding: 8px 14px; cursor: pointer; border-radius: 2px;
}
#evict:hover { border-color: var(--lamp-dim); color: var(--lamp); }

@media (max-width: 640px) {
  .station { min-width: 120px; }
}
</style>
