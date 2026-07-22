<script setup>
import {Checkbox, NumberInput, Textarea} from '@script-development/ui-inputs';
import {onMounted, onUnmounted, ref} from 'vue';
import LogWell from '../components/LogWell.vue';
import PottersWheel from '../components/PottersWheel.vue';
import {api} from '../composables/useBoothApi.js';
import {createJobPoller} from '../composables/useJobPoller.js';
import {openTab} from '../stores/booth.js';

const subject = ref('');
const twoSided = ref(false);
const octree = ref(128);
const threshold = ref(0.5);
const seed = ref(null); // null = the kiln picks (NumberInput's honest empty)
const busy = ref(false);
const error = ref('');
const logLines = ref([]);
const logShown = ref(false);
const candidate = ref(null);
const fired = ref(false);

const poller = createJobPoller({
    fetchJob: () => api('/api/kiln/job'),
    intervalMs: 3000,
    onTick: job => {
        logLines.value = job.log_tail || [];
    },
    onSettled: job => {
        busy.value = false;
        if (job.state === 'done' && job.candidate) candidate.value = job.candidate;
        else if (job.state === 'failed') error.value = job.error || 'The firing collapsed — the log above names where.';
    },
    onLost: () => {
        busy.value = false;
        error.value = 'The booth lost sight of the kiln — the server stopped answering. Reload to reconnect; the firing may still land on the Curing Rack.';
    },
});

async function fire() {
    error.value = '';
    if (!subject.value.trim()) {
        error.value = 'The kiln fires nothing from an empty subject — name the prop.';
        return;
    }
    busy.value = true;
    try {
        await api('/api/kiln/generate', {
            subject: subject.value.trim(),
            octree: Number(octree.value) || 128,
            threshold: Number(threshold.value) || 0.5,
            two_sided: twoSided.value,
            seed: seed.value ?? undefined,
        });
        candidate.value = null;
        fired.value = true;
        logShown.value = true;
        poller.start();
    } catch (e) {
        busy.value = false;
        error.value = e.message || String(e);
    }
}

const chipRows = c => {
    const rows = [[`seed ${c.seed}`, 'chip'], [c.orient_hint, 'chip']];
    rows.push(c.refire_count ? [`refired · ${c.octree}`, 'chip scar'] : [`octree ${c.octree}`, 'chip']);
    if (c.two_sided) rows.push(['two-sided', 'chip']);
    return rows;
};

onMounted(async () => {
    // resume watching if a firing is already burning when the room opens
    try {
        const job = await api('/api/kiln/job');
        if (job.state === 'running') {
            logShown.value = true;
            busy.value = true;
            fired.value = true;
            poller.start();
        }
    } catch {
        // the booth may be dark — the first firing will say so
    }
});
onUnmounted(poller.stop);
</script>

<template>
  <div class="panel">
    <label class="field" for="kiln-subject">What are we firing?</label>
    <Textarea id="kiln-subject" v-model="subject" placeholder="a black omafiets leaning at a slight angle" />
    <Checkbox id="kiln-two-sided" v-model="twoSided" label="Two-sided — declare asymmetry; the room won't guess" />
    <details class="kiln-settings">
      <summary>Kiln settings · the defaults are the prop-dressing laws</summary>
      <div class="row">
        <div><label class="field" for="kiln-octree">Octree</label>
          <NumberInput id="kiln-octree" v-model="octree" :min="16" :max="512" :step="16" />
          <p class="knob-note">The carving grid — how finely the mesher subdivides space.
            Higher keeps thin parts (chair legs, spokes) from shredding, but fires slower
            and the GLB weighs more. A firing that tatters at 128 auto-refires at 224.</p></div>
        <div><label class="field" for="kiln-threshold">Threshold</label>
          <NumberInput id="kiln-threshold" v-model="threshold" :min="0.1" :max="1" :step="0.05" />
          <p class="knob-note">Where the skin gets drawn in the voxel field. Lower is more
            generous — thin features survive as material; higher cuts tighter and can eat
            them. The auto-refire softens to 0.4 for exactly that reason.</p></div>
        <div><label class="field" for="kiln-seed">Seed</label>
          <NumberInput id="kiln-seed" v-model="seed" placeholder="the kiln picks" />
          <p class="knob-note">The dice — one seed steers both the painting and the mesh,
            so the same subject with the same seed fires the same prop again. Leave it
            blank and the kiln rolls fresh every firing.</p></div>
      </div>
    </details>
    <button id="kiln-go" class="fire" :disabled="busy" @click="fire">{{ busy ? 'Firing…' : 'Fire it' }}</button>
    <p class="note">The kiln fires the subject on a palette-disjoint chroma ground, keys it
      clean (border alpha lands at exactly 0 or the firing is refused), meshes it through
      Hunyuan3D, and checks the silhouette before you see it. A thin structure that
      tatters at 128 is refired once at 224 — the room remembers the laws so you don't.</p>
    <p v-show="error" class="error">{{ error }}</p>
    <LogWell :lines="logLines" :shown="logShown" />
    <div id="kiln-result" class="result">
      <p v-if="!candidate && !fired" class="empty">No firing yet — name a subject and the kiln lights.</p>
      <figure v-if="candidate" :key="candidate.id" class="mount">
        <div class="mount-frame">
          <PottersWheel
            :glb-url="`/kiln-output/${candidate.id}/${candidate.id}.glb`"
            :poster-src="`/kiln-output/${candidate.id}/turn/000.png`"
            :poster-alt="candidate.subject"
            hint="take it by the rim — drag to see every side"
          />
          <span class="mount-stamp">{{ candidate.refire_count ? 'Fired · mended' : 'Fired' }}</span>
        </div>
        <figcaption class="mount-body">
          <p class="mount-title">{{ candidate.subject }}</p>
          <div class="mount-chips">
            <span v-for="([text, cls], i) in chipRows(candidate)" :key="i" :class="cls">{{ text }}</span>
          </div>
          <div class="mount-acts">
            <button class="act" @click="openTab('rack')">→ On the Curing Rack</button>
          </div>
        </figcaption>
      </figure>
    </div>
  </div>
</template>

<style>
details.kiln-settings { margin-top: 14px; }
details.kiln-settings summary {
  cursor: pointer; font-size: 11px; letter-spacing: .16em; text-transform: uppercase;
  color: var(--dim);
}
details.kiln-settings summary:hover { color: var(--lamp); }
details.kiln-settings .row { margin-top: 10px; }
details.kiln-settings .knob-note {
  margin: 6px 0 0; max-width: 250px;
  font-size: 11.5px; font-style: italic; color: var(--dim); line-height: 1.55;
}
/* the .sided checkbox grammar moved to src/ui-inputs-map.css (.ui-check) —
   the Checkbox atom is the row now, lamp fill via --ui-check-bg-checked */
</style>
