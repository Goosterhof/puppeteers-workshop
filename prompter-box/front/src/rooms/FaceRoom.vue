<script setup>
import {onMounted, onUnmounted, ref} from 'vue';
import StampedMount from '../components/StampedMount.vue';
import ThumbRow from '../components/ThumbRow.vue';
import {api} from '../composables/useBoothApi.js';
import {createJobPoller} from '../composables/useJobPoller.js';
import {loadArchive} from '../stores/archive.js';
import {castAsLead, facePrompt, faceSitter, leadRes, openTab} from '../stores/booth.js';
import {nearestResolution} from '../lib/resolution.js';

const painters = ref([]);
const painter = ref('');
const width = ref(768);
const height = ref(1024);
const seed = ref(7);
const busy = ref(false);
const painting = ref(false);
const error = ref('');
const results = ref(null);

// In edit mode the output follows the sitter's dimensions (~1 MP).
const pickSitter = name => {
    faceSitter.value = faceSitter.value === name ? null : name;
};

async function loadPainters() {
    try {
        const {painters: list, default: def} = await api('/api/face/models');
        painters.value = list;
        if (def) painter.value = def;
    } catch {
        // storeroom unreadable — the server falls back to the house painter
    }
}
onMounted(loadPainters);

let poller = null;
onUnmounted(() => poller?.stop());

// ComfyUI's history reports [event, {node_type, exception_message, …}] pairs.
const brokenBrush = detail => (detail || [])
    .map(m => (Array.isArray(m) ? m[1] : m) || {})
    .map(d => (d.exception_message ? `${d.node_type ? `${d.node_type}: ` : ''}${d.exception_message}` : ''))
    .filter(Boolean).join('\n');

function showPaintings(files, cue) {
    results.value = files.map(f => ({
        url: `/face-output/${encodeURIComponent(f)}`,
        title: cue.prompt || f,
        meta: {model: cue.model, seed: cue.seed},
        acts: [{label: 'Send to the stage →', run: async ({el}) => {
            await castAsLead(f);
            const img = el?.querySelector('img');
            if (img?.naturalWidth) leadRes.value = {w: img.naturalWidth, h: img.naturalHeight};
            openTab('stage');
        }}],
    }));
}

async function cue() {
    error.value = '';
    busy.value = true;
    // the recipe as cued — captured now, so the mount stays truthful if the form changes mid-paint
    const cued = {prompt: facePrompt.value.trim(), seed: Number(seed.value),
        model: (painter.value || '').replace(/\.(gguf|safetensors)$/i, '')};
    try {
        const {prompt_id} = await api('/api/face/generate', {
            prompt: facePrompt.value, width: Number(width.value), height: Number(height.value), seed: Number(seed.value),
            model: painter.value || undefined, source: faceSitter.value || undefined,
        });
        results.value = [];
        painting.value = true;
        poller?.stop();
        poller = createJobPoller({
            // the Face Shop speaks 'painting' where the stage says 'running'
            fetchJob: async () => {
                const r = await api(`/api/face/result/${prompt_id}`);
                return {...r, state: r.state === 'painting' ? 'running' : r.state};
            },
            intervalMs: 1500,
            onSettled: r => {
                busy.value = false;
                painting.value = false;
                if (r.state === 'done') {
                    showPaintings(r.images, cued);
                    loadArchive();
                } else {
                    const detail = brokenBrush(r.detail);
                    error.value = detail
                        ? `The Face Shop rejected the cue — the broken brush:\n${detail}`
                        : 'The Face Shop rejected the cue — it kept the reason to itself; the ComfyUI log names the brush that broke.';
                }
            },
            onLost: e => {
                busy.value = false;
                painting.value = false;
                error.value = `The booth lost sight of the Face Shop — ${e?.message || 'the server stopped answering'}. Reload to reconnect; the painting may still land in The Canisters.`;
            },
        });
        poller.start();
    } catch (e) {
        busy.value = false;
        error.value = e.message || String(e);
    }
}
</script>

<template>
  <div class="panel">
    <label class="field" for="face-model">The painter — from ComfyUI's storeroom</label>
    <select id="face-model" v-model="painter">
      <option v-for="name in painters" :key="name" :value="name">{{ name }}</option>
    </select>
    <label class="field" for="face-prompt">The cue</label>
    <textarea id="face-prompt" v-model="facePrompt"></textarea>
    <label class="field">The sitter — optional: an image to EDIT; the cue then describes the change (click to pick, click again to clear)</label>
    <ThumbRow id="face-thumbs" :picked="faceSitter" @pick="pickSitter" />
    <div class="row" style="margin-top:14px">
      <div><label class="field" for="face-w">Width</label><input id="face-w" v-model="width" type="number" step="16" :disabled="!!faceSitter"></div>
      <div><label class="field" for="face-h">Height</label><input id="face-h" v-model="height" type="number" step="16" :disabled="!!faceSitter"></div>
      <div><label class="field" for="face-seed">Seed</label><input id="face-seed" v-model="seed" type="number"></div>
      <div><button id="face-go" class="fire" style="margin-top:0" :disabled="busy" @click="cue">Cue the face shop</button></div>
    </div>
    <p class="note">The house painter is Flux 2 Klein 9B, 4-step distilled — a take lands in seconds once warm. With a sitter picked the painter EDITS instead of painting fresh (the night-crier ReferenceLatent recipe): the cue describes the change — "repaint him as…", "replace the background with…", "swap the woman into…" — and width/height follow the sitter. The qwen3 text encoder and flux2 VAE are bolted to the easel, so only Flux 2 family painters will pair; drop new ones in <code>ComfyUI/models/diffusion_models/</code> and they appear here. (Krea 2 paints via the Stage — pick it a lead and it repaints at the strength knob.)</p>
    <p v-show="error" class="error">{{ error }}</p>
    <div id="face-result" class="result">
      <p v-if="results === null" class="empty">No painting yet — cue the face shop and it hangs here.</p>
      <span v-else-if="painting" class="cap">Painting…</span>
      <StampedMount
        v-for="r in results || []" :key="r.url"
        room="face" :url="r.url" kind="image" :title="r.title" :meta="r.meta" :acts="r.acts"
      />
    </div>
  </div>
</template>
