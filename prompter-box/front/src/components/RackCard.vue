<script setup>
import {NumberInput, TextInput} from '@script-development/ui-inputs';
import {computed, onUnmounted, ref} from 'vue';
import PottersWheel from './PottersWheel.vue';
import {api} from '../composables/useBoothApi.js';
import {slugify} from '../lib/slugify.js';

// One candidate on the Curing Rack — grid strip or spotlight. Judgment
// happens here: Approve shelves, Refire re-meshes the SAME painting,
// Discard hands the entry to the break-pit.
const props = defineProps({
    entry: {type: Object, required: true},
    onWheel: {type: Boolean, default: false},
    spinFrame: {type: Number, default: 0},
    mended: {type: Boolean, default: false},
    spotlit: {type: Boolean, default: false},
    outerError: {type: String, default: ''},
});
const emit = defineEmits(['spotlight', 'reload', 'discard']);

const mode = ref('');
const packName = ref(slugify(props.entry.recipe.canister_label || props.entry.recipe.subject));
const refOctree = ref(224);
const refThreshold = ref(0.4);
const refiring = ref(false);
const localError = ref('');
const shownError = computed(() => localError.value || props.outerError);
let refireTimer = null;
onUnmounted(() => clearInterval(refireTimer));

const r = computed(() => props.entry.recipe);
const frames = computed(() => props.entry.frames || []);
// the wheel takes the piece at the exact yaw the strip was showing — the
// frame freezes at spotlight time, the grid keeps turning
const frozenFrame = props.spinFrame;
const stripSrc = computed(() => frames.value.length
    ? `/kiln-output/${frames.value[(props.onWheel ? frozenFrame : props.spinFrame) % frames.value.length]}` : '');

const verdict = computed(() => {
    if (!props.entry.qa) return {cls: 'curing', word: 'CURING…'};
    return props.entry.qa.passed ? {cls: 'cured', word: 'CURED'} : {cls: 'tattered', word: 'TATTERED'};
});
const qaLine = computed(() => {
    const rec = r.value;
    const qa = props.entry.qa;
    if (rec.refire_count > 0 && qa && qa.passed) return `the silhouette tattered — the refire at ${rec.octree} closed it.`;
    if (rec.refire_count > 0 && (rec.shredding_detected || (qa && !qa.passed))) return 'still tattering after refire — needs a look.';
    if (qa && !qa.passed) return qa.failure_reason;
    return '';
});
const chips = computed(() => {
    const rows = [[r.value.orient_hint, 'chip']];
    rows.push(r.value.refire_count > 0 ? [`refired · ${r.value.octree}`, 'chip scar'] : [`octree ${r.value.octree}`, 'chip']);
    rows.push([`seed ${r.value.seed}`, 'chip']);
    if (r.value.two_sided) rows.push(['two-sided', 'chip']);
    return rows;
});

const nameOk = computed(() => /^[a-z0-9-]+$/.test(packName.value.trim()));
async function shelve() {
    const name = packName.value.trim();
    if (!nameOk.value) {
        localError.value = `'${name}' will not survive the packer — lowercase letters, digits, and dashes only.`;
        return;
    }
    try {
        await api('/api/rack/approve', {candidate_id: props.entry.id, pack_name: name});
        emit('reload');
    } catch (e) {
        localError.value = e.message;
    }
}
async function refire() {
    try {
        await api('/api/rack/refire', {candidate_id: props.entry.id, octree: Number(refOctree.value), threshold: Number(refThreshold.value)});
        refiring.value = true;
        refireTimer = setInterval(async () => {
            try {
                const job = await api('/api/kiln/job');
                if (job.state === 'running') return;
                clearInterval(refireTimer);
                emit('reload'); // the mended candidate deals in with its ember scar
            } catch {
                clearInterval(refireTimer);
            }
        }, 3000);
    } catch (e) {
        localError.value = e.message;
    }
}
</script>

<template>
  <article
    class="canister candidate"
    :class="{spotlight: onWheel, mended, spotlit}" :data-id="entry.id"
  >
    <PottersWheel
      v-if="onWheel && frames.length"
      class="well"
      :glb-url="`/kiln-output/${entry.id}/${entry.id}.glb`"
      :initial-yaw="2 * Math.PI * (frozenFrame % 8) / 8"
      :poster-src="stripSrc"
      :poster-alt="r.canister_label || r.subject"
    >
      <span class="qa-badge" :class="verdict.cls">{{ verdict.word }}</span>
    </PottersWheel>
    <div
      v-else class="well" :class="{shelf: frames.length}"
      :title="frames.length ? 'Put it on the Potter\'s Wheel' : undefined"
      @click="frames.length && emit('spotlight')"
    >
      <img v-if="frames.length" class="spin" :src="stripSrc" :alt="r.canister_label || r.subject">
      <span v-else class="no-spin">◌</span>
      <span class="qa-badge" :class="verdict.cls">{{ verdict.word }}</span>
    </div>
    <div class="body">
      <p class="title">{{ r.canister_label || r.subject }}</p>
      <div class="chips">
        <span v-for="([text, cls], i) in chips" :key="i" :class="cls">{{ text }}</span>
      </div>
      <p v-if="qaLine" class="qa-line">{{ qaLine }}</p>
      <div class="acts">
        <button class="fire" @click="mode = 'approve'">Approve</button>
        <button class="act" @click="mode = 'refire'">Refire</button>
        <button class="act breaker" @click="emit('discard', entry)">Discard</button>
        <button v-if="onWheel" class="act" @click="emit('spotlight')">✕ Off the wheel</button>
      </div>
      <div v-if="mode === 'approve'" class="approve-row">
        <TextInput :id="`pack-name-${entry.id}`" v-model="packName" :invalid="!nameOk" />
        <button class="fire" style="margin-top:0" @click="shelve">Shelve it</button>
      </div>
      <template v-if="mode === 'refire'">
        <div class="refire-row">
          <NumberInput :id="`refire-octree-${entry.id}`" v-model="refOctree" :step="16" title="octree" />
          <NumberInput :id="`refire-threshold-${entry.id}`" v-model="refThreshold" :step="0.05" title="threshold" />
          <button class="act" :disabled="refiring" @click="refire">{{ refiring ? 'Refiring…' : 'Refire' }}</button>
        </div>
        <p class="qa-line refire-note">Same painting, new firing — a full repaint starts back at the Kiln.</p>
      </template>
      <p v-show="shownError" class="error">{{ shownError }}</p>
    </div>
  </article>
</template>

<style>
.candidate .well img.still { width: 100%; height: 148px; object-fit: contain; display: block; }
.candidate { cursor: default; animation: deal .35s ease-out backwards; }
.candidate:nth-child(2) { animation-delay: .08s; }
.candidate:nth-child(3) { animation-delay: .16s; }
.candidate:nth-child(4) { animation-delay: .24s; }
.candidate .well {
  position: relative; height: 148px; background: #0d0b08;
  display: flex; align-items: center; justify-content: center;
}
.candidate .well img.spin { width: 100%; height: 148px; object-fit: contain; display: block; }
.candidate .well .no-spin { color: var(--curing); font-size: 26px; }
.candidate .well.shelf { cursor: pointer; }
.candidate .well.shelf:hover { box-shadow: inset 0 0 0 1px var(--lamp-dim); }
.candidate.spotlit { border-color: var(--lamp); }
.candidate .act.breaker:hover { border-color: var(--tattered); color: var(--tattered); }
.candidate.spotlight { max-width: 860px; width: 100%; animation: none; }
.candidate.spotlight .well { height: min(56vh, 520px); }
.candidate.spotlight .well img { width: 100%; height: 100%; object-fit: contain; }
.qa-badge {
  position: absolute; top: 0; right: 0; z-index: 2;
  font: 11px var(--display); letter-spacing: .2em; text-transform: uppercase; color: var(--ink);
  padding: 4px 12px 4px 10px;
  clip-path: polygon(12px 0, 100% 0, 100% 100%, 0 100%);
}
.qa-badge.cured    { background: var(--cured); }
.qa-badge.tattered { background: var(--tattered); color: var(--paper); }
.qa-badge.curing   { background: var(--curing); }
.chip.scar { color: var(--ember); border-color: var(--ember-dim); }
@keyframes mend {           /* ember-flare: the scar glows hot, then settles */
  0%   { box-shadow: 0 0 0 rgba(204,107,51,0);   color: var(--ember); }
  35%  { box-shadow: 0 0 14px rgba(204,107,51,.7); color: var(--filament); }
  100% { box-shadow: 0 0 0 rgba(204,107,51,0);   color: var(--ember); }
}
.candidate.mended .chip.scar { animation: mend .9s ease-out; }
.candidate .qa-line { font-size: 11.5px; font-style: italic; color: var(--dim);
                      margin-top: 8px; line-height: 1.45; }
.candidate .acts { display: flex; gap: 8px; margin-top: 10px; align-items: center; flex-wrap: wrap; }
.candidate .acts .fire { margin-top: 0; padding: 8px 16px; font-size: 11px; }
.candidate .act {
  background: none; border: 1px solid var(--drape-edge); color: var(--dim);
  font: 11px var(--display); letter-spacing: .16em; text-transform: uppercase;
  padding: 7px 12px; cursor: pointer; border-radius: 2px;
}
.candidate .act:hover { border-color: var(--lamp-dim); color: var(--lamp); }
.candidate .approve-row, .candidate .refire-row { margin-top: 10px; display: flex; gap: 6px; }
.candidate .approve-row input[type=text] { font-size: 12px; padding: 7px 9px; }
.candidate .refire-row input { width: 64px; font-size: 12px; padding: 7px 6px; }
</style>
