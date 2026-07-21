<script setup>
import {computed, onMounted, onUnmounted, ref, watch} from 'vue';
import LogWell from '../components/LogWell.vue';
import StampedMount from '../components/StampedMount.vue';
import ThumbRow from '../components/ThumbRow.vue';
import {api} from '../composables/useBoothApi.js';
import {createJobPoller} from '../composables/useJobPoller.js';
import {loadArchive} from '../stores/archive.js';
import {castAsLead, leadRes, loadFoleySources, openTab, pickedImage, stagePrompt} from '../stores/booth.js';
import {nearestResolution, RES_PRESETS} from '../lib/resolution.js';

const KIND_LABEL = {i2v: 'image → video', t2v: 'text → video', swap: 'motion transfer', t2i: 'text → image'};
const LEAD_LABEL = {
    i2v: 'The lead — start image (footage/)',
    t2v: 'The lead — optional: hand it a start image, or let it work from text alone',
    swap: 'The lead — the character to animate (footage/)',
    t2i: 'The lead — optional: pick a source to repaint (img2img at the strength below), or paint from text alone',
};

const models = ref([]);
const modelType = ref('');
const guides = ref({footage: [], stage: []});
const guide = ref('');
const garments = ref([]);
const resOptions = ref(RES_PRESETS.video);
const resolution = ref('704x1280');
const length = ref(41);
const strength = ref(0.6);
const steps = ref(4);
const guidance = ref(1);
const seed = ref(7);
const note = ref('Wan 2.2 i2v Enhanced Lightning 14B — the identity-holding recipe from the bell-swing arc. First run after cold start adds model-load minutes.');
const error = ref('');
const logLines = ref([]);
const logShown = ref(false);
const results = ref(null);

const performer = () => models.value.find(m => m.type === modelType.value);
const kind = computed(() => performer()?.kind);
const isImage = computed(() => kind.value === 't2i');

function applyPerformer() {
    const m = performer();
    if (!m) return;
    const presets = isImage.value ? RES_PRESETS.image : RES_PRESETS.video;
    resOptions.value = presets.includes(m.resolution) ? presets : [m.resolution, ...presets];
    resolution.value = m.resolution;
    if (!isImage.value) length.value = m.video_length;
    steps.value = m.steps;
    guidance.value = m.guidance;
    note.value = m.note || `${m.name} — enumerated fresh from the workshop floor.`;
    garments.value = m.loras.map(name => ({name, on: false, mult: '1.0'}));
    if (m.kind === 'swap') loadGuides();
}
watch(modelType, applyPerformer);

// a cast lead arrived from another room — match the aspect, once
watch(leadRes, v => {
    if (!v) return;
    resolution.value = nearestResolution(resOptions.value, v.w, v.h);
    leadRes.value = null;
});

async function loadModels() {
    try {
        const {models: list, default: def} = await api('/api/stage/models');
        models.value = list;
        if (def) modelType.value = def;
        else applyPerformer();
    } catch (e) {
        error.value = e.message || String(e);
    }
}

async function loadGuides() {
    const keep = guide.value;
    guides.value = await api('/api/foley/sources');
    const known = [...guides.value.stage.map(n => `stage:${n}`), ...guides.value.footage.map(n => `footage:${n}`)];
    guide.value = known.includes(keep) ? keep : '';
}

const pickThumb = name => {
    pickedImage.value = pickedImage.value === name ? null : name;
};
const donned = () => {
    const loras = [];
    const mults = [];
    for (const g of garments.value) {
        if (g.on) {
            loras.push(g.name);
            mults.push(Number(g.mult) || 1);
        }
    }
    return {loras, mults};
};

function validate(m) {
    if (!m) return 'No performer selected — the playbill may still be loading.';
    if ((m.kind === 'i2v' || m.kind === 'swap') && !pickedImage.value) {
        return m.kind === 'swap'
            ? `${m.name} needs a lead — the character to animate. Pick one from the footage.`
            : 'The Stage needs a lead — pick a start image from the footage.';
    }
    if (m.kind === 'swap' && !guide.value) return `${m.name} needs choreography — pick a driving video.`;
    return '';
}

async function cue() {
    error.value = '';
    const m = performer();
    const objection = validate(m);
    if (objection) {
        error.value = objection;
        return;
    }
    try {
        const {loras, mults} = donned();
        await api('/api/stage/generate', {
            model_type: m.type,
            prompt: stagePrompt.value,
            image: pickedImage.value || '',
            video_guide: m.kind === 'swap' ? guide.value : undefined,
            strength: m.kind === 't2i' ? Number(strength.value) : undefined,
            resolution: resolution.value, video_length: Number(length.value), seed: Number(seed.value),
            steps: Number(steps.value) || undefined, guidance: Number(guidance.value),
            loras, lora_multipliers: mults,
        });
        results.value = [];
        logShown.value = true;
        poller.start();
    } catch (e) {
        error.value = e.message || String(e);
    }
}

function takeMount(f, job) {
    const image = /\.(png|jpe?g|webp)$/i.test(f);
    return {
        url: `/stage-output/${encodeURIComponent(f)}`,
        kind: image ? 'image' : 'video',
        title: f,
        meta: {model: job.model, seed: job.seed,
            loras: (job.loras || []).map(l => l.replace(/\.safetensors$/i, ''))},
        acts: image
            ? [{label: 'Cast as a lead →', run: async ({relabel}) => {
                await castAsLead(f, 'stage');
                relabel('Cast — it is in the footage now');
            }}]
            : [{label: 'Score it in the foley booth →', run: async () => {
                await loadFoleySources(`stage:${f}`);
                openTab('foley');
            }}],
    };
}

const poller = createJobPoller({
    fetchJob: () => api('/api/stage/job'),
    intervalMs: 3000,
    onTick: job => {
        logLines.value = job.log_tail || [];
    },
    onSettled: job => {
        if (job.state === 'done') {
            results.value = (job.outputs || []).map(f => takeMount(f, job));
            loadArchive();
        } else if (job.state === 'failed') {
            error.value = `The take collapsed (exit ${job.exit_code}). The last lines of the log above tell you where — fix the cue and call it again.`;
        }
    },
    onLost: () => {
        error.value = 'The booth lost sight of the stage — the server stopped answering. Reload to reconnect; the take may still be running and will land in The Canisters.';
    },
});

onMounted(async () => {
    loadModels();
    // resume watching if a take is already running when the room opens
    try {
        const job = await api('/api/stage/job');
        if (job.state === 'running') {
            logShown.value = true;
            poller.start();
        }
    } catch {
        // the booth may be dark — the first cue will say so
    }
});
onUnmounted(poller.stop);
</script>

<template>
  <div class="panel">
    <label class="field" for="stage-model">The performer — every model with weights on the floor</label>
    <select id="stage-model" v-model="modelType">
      <option v-for="m in models" :key="m.type" :value="m.type">{{ m.name }} · {{ KIND_LABEL[m.kind] || m.kind }}</option>
    </select>
    <label class="field" for="stage-prompt">The cue</label>
    <textarea id="stage-prompt" v-model="stagePrompt"></textarea>
    <label id="stage-lead-label" class="field">{{ LEAD_LABEL[kind] || 'The lead' }}</label>
    <ThumbRow id="thumbs" :picked="pickedImage" @pick="pickThumb" />
    <div v-show="kind === 'swap'" id="stage-guide-row">
      <label class="field" for="stage-guide">The choreography — the driving video whose motion the character re-performs</label>
      <select id="stage-guide" v-model="guide">
        <option value="">— pick the choreography —</option>
        <optgroup v-if="guides.stage.length" label="Stage takes">
          <option v-for="n in guides.stage" :key="n" :value="`stage:${n}`">{{ n }}</option>
        </optgroup>
        <optgroup v-if="guides.footage.length" label="Footage">
          <option v-for="n in guides.footage" :key="n" :value="`footage:${n}`">{{ n }}</option>
        </optgroup>
      </select>
    </div>
    <div v-show="garments.length" id="stage-lora-row">
      <label class="field">The wardrobe — LoRAs on this performer's shelf (click to don, then set the strength)</label>
      <div id="stage-loras" class="lorarack">
        <div v-for="g in garments" :key="g.name" class="garment">
          <button :title="g.name" :data-lora="g.name" :aria-pressed="g.on" @click="g.on = !g.on">{{ g.name.replace(/\.safetensors$/i, '') }}</button>
          <input v-model="g.mult" type="number" step="0.05" :disabled="!g.on" title="strength">
        </div>
      </div>
      <p id="stage-lora-note" class="note">Accelerator LoRAs (FastWan and kin) usually want few steps and guidance 1 — the knobs below are yours.</p>
    </div>
    <div class="row" style="margin-top:14px">
      <div><label class="field" for="stage-res">Resolution</label>
        <select id="stage-res" v-model="resolution">
          <option v-for="r in resOptions" :key="r">{{ r }}</option>
        </select></div>
      <div v-show="!isImage" id="stage-len-wrap"><label class="field" for="stage-len">Frames</label><input id="stage-len" v-model="length" type="number" min="9" step="4"></div>
      <div v-show="isImage" id="stage-strength-wrap"><label class="field" for="stage-strength">Strength</label><input id="stage-strength" v-model="strength" type="number" min="0.05" max="1" step="0.05"></div>
      <div><label class="field" for="stage-steps">Steps</label><input id="stage-steps" v-model="steps" type="number" min="1" max="100"></div>
      <div><label class="field" for="stage-guidance">Guidance</label><input id="stage-guidance" v-model="guidance" type="number" min="0" step="0.5"></div>
      <div><label class="field" for="stage-seed">Seed</label><input id="stage-seed" v-model="seed" type="number"></div>
      <div><button id="stage-go" class="fire" style="margin-top:0" @click="cue">Cue the stage</button></div>
    </div>
    <p id="stage-note" class="note">{{ note }}</p>
    <p v-show="error" class="error">{{ error }}</p>
    <LogWell :lines="logLines" :shown="logShown" />
    <div id="stage-result" class="result">
      <p v-if="results === null" class="empty">No take yet — cue the stage and the reel mounts here.</p>
      <StampedMount
        v-for="r in results || []" :key="r.url"
        room="stage" :url="r.url" :kind="r.kind" :title="r.title" :meta="r.meta" :acts="r.acts"
      />
    </div>
  </div>
</template>

<style>
.lorarack { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.lorarack .garment { display: flex; align-items: center; gap: 6px; }
.lorarack .garment button {
  background: var(--booth); border: 1px solid var(--drape-edge); color: var(--dim);
  font: 12px var(--typed); padding: 7px 12px; cursor: pointer; border-radius: 2px;
  max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.lorarack .garment button[aria-pressed="true"] { border-color: var(--lamp); color: var(--lamp); }
.lorarack .garment input { width: 64px; padding: 6px 6px; }
.lorarack .garment input:disabled { opacity: .35; }
</style>
