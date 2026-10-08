<script setup lang="ts">
import {NumberInput, SingleSelect, Textarea} from '@script-development/ui-inputs';
import {computed, onMounted, onUnmounted, ref, watch} from 'vue';
import RoomFlow from '../components/RoomFlow.vue';
import StampedMount from '../components/StampedMount.vue';
import ThumbRow from '../components/ThumbRow.vue';
import {api} from '../composables/useBoothApi';
import {createJobPoller} from '../composables/useJobPoller';
import type {JobPoller} from '../composables/useJobPoller';
import {readFaceWorkbench, saveFaceWorkbench, stillUrl} from '../lib/face-workbench';
import type {FaceRecipe, FaceRevision, StillAsset} from '../lib/face-workbench';
import {loadArchive} from '../stores/archive';
import {castAsLead, faceHandoff, facePrompt, faceSitter, forgeIdea, forgeLead, forgeTarget, leadRes, openTab, refineStill, stageTaskHandoff} from '../stores/booth';
import {faceRecipeHandoff} from '../stores/pins';

defineOptions({inheritAttrs: false});

interface BrushFault {node_type?: string; exception_message?: string}
interface FaceJob {state?: string; images?: string[]; detail?: (BrushFault | [string, BrushFault])[]}

const saved = readFaceWorkbench();
const restore = !faceSitter.value && !facePrompt.value;
if (saved && restore) {
    faceSitter.value = saved.draft.source;
    facePrompt.value = saved.draft.prompt;
}
const painters = ref<string[]>([]);
const paintersReady = ref(false);
const painterError = ref('');
const requestedPainter = ref('');
const painter = ref(saved && restore ? saved.draft.model : '');
const painterOptions = computed(() => painters.value.map(name => ({id: name, label: name})));
const width = ref(saved && restore ? saved.draft.width : 768);
const height = ref(saved && restore ? saved.draft.height : 1024);
const seed = ref(saved && restore ? saved.draft.seed : 7);
const mode = ref(faceSitter.value ? 'refine' : 'create');
const busy = ref(false);
const error = ref('');
const formulaNote = ref('');
const original = ref<StillAsset | null>(saved && restore ? saved.original : faceSitter.value ? {room: 'footage', name: faceSitter.value} : null);
const revisions = ref<FaceRevision[]>(saved && restore ? saved.revisions : []);
const selected = ref<string | null>(saved && restore ? saved.selected : null);
const pending = ref(saved && restore ? saved.pending : null);
const comparison = ref('source');
const changeKeep = ref(saved && restore ? saved.draft.keep || '' : '');
const transferring = ref(false);
const current = computed(() => revisions.value.find(r => r.name === selected.value) ?? null);
const sitter = computed<StillAsset | null>(() => faceSitter.value ? {room: 'footage', name: faceSitter.value} : null);
const compareAsset = computed(() => comparison.value === 'original' ? original.value : current.value?.source ?? sitter.value);
const currentUrl = computed(() => current.value ? stillUrl({room: 'face', name: current.value.name}) : '');
const progress = computed(() => busy.value ? 2 : current.value ? 3 : facePrompt.value.trim() ? 2 : faceSitter.value ? 1 : 0);

function persist() {
    saveFaceWorkbench({original: original.value, revisions: revisions.value, selected: selected.value,
        draft: {prompt: facePrompt.value, source: faceSitter.value, width: Number(width.value), height: Number(height.value), seed: Number(seed.value), model: painter.value, keep: changeKeep.value},
        pending: pending.value});
}
watch([facePrompt, faceSitter, width, height, seed, painter, changeKeep, original, revisions, selected, pending], persist, {deep: true});
watch(faceSitter, source => {
    if (source) {
        mode.value = 'refine';
        if (!original.value) original.value = {room: 'footage', name: source};
    }
});

interface CharacterChange {
    source: string | null;
    original: StillAsset | null;
    resetHistory: boolean;
    recipe?: Record<string, unknown>;
    prompt?: string;
}
const resetDialog = ref<HTMLDialogElement | null>(null);
let nextCharacter: CharacterChange | null = null;
function startBench(change: CharacterChange) {
    faceSitter.value = change.source;
    mode.value = change.source ? 'refine' : 'create';
    if (change.resetHistory) {
        original.value = change.original;
        revisions.value = [];
        selected.value = null;
        changeKeep.value = '';
    }
    if (change.recipe) { formulaNote.value = ''; applyRecipe(change.recipe); }
    if (change.prompt !== undefined) facePrompt.value = change.prompt;
    error.value = '';
}
function requestBench(change: CharacterChange) {
    if (busy.value || pending.value || transferring.value) return;
    if (change.resetHistory && revisions.value.length) {
        nextCharacter = change;
        resetDialog.value?.showModal();
    } else startBench(change);
}
function cancelNewBench() {
    nextCharacter = null;
    resetDialog.value?.close();
}
function confirmNewBench() {
    const change = nextCharacter;
    cancelNewBench();
    if (change && !busy.value && !pending.value && !transferring.value) startBench(change);
}
function chooseMode(next: string) {
    if (next === mode.value) return;
    if (next === 'create') requestBench({source: null, original: null, resetHistory: true});
    else mode.value = 'refine';
}
function pickSitter(name: string) {
    if (name === faceSitter.value) return;
    requestBench({source: name, original: {room: 'footage', name}, resetHistory: true});
}
function matchRequestedPainter() {
    if (!paintersReady.value || !requestedPainter.value) return;
    const name = requestedPainter.value;
    const match = painters.value.find(p => p.replace(/\.(gguf|safetensors)$/i, '') === name);
    if (match) { painter.value = match; requestedPainter.value = ''; }
    else formulaNote.value = `The recipe's painter “${name}” is absent. Choose an available painter in Advanced settings.`;
}
watch(paintersReady, matchRequestedPainter);
function applyRecipe(r: Record<string, unknown>) {
    if (typeof r.prompt === 'string') facePrompt.value = r.prompt;
    if (r.seed !== undefined && Number.isFinite(Number(r.seed))) seed.value = Number(r.seed);
    if (typeof r.resolution === 'string') {
        const [w, h] = r.resolution.split('x').map(Number);
        if (w && h) { width.value = w; height.value = h; }
    }
    requestedPainter.value = typeof r.model === 'string' ? r.model.replace(/\.(gguf|safetensors)$/i, '') : '';
    matchRequestedPainter();
}
watch(faceRecipeHandoff, handoff => {
    if (!handoff) return;
    formulaNote.value = `Wearing “${handoff.name}” — cue, seed and dimensions restored; painter matched when the roster answers.`;
    applyRecipe(handoff.recipe);
    faceRecipeHandoff.value = null;
}, {immediate: true});
watch([faceHandoff, busy, pending, transferring], ([handoff]) => {
    if (!handoff || busy.value || pending.value || transferring.value) return;
    const knownVersion = handoff.asset.room === 'face' && revisions.value.some(r => r.name === handoff.asset.name);
    // The old cue belongs to the old take; the handoff's explicit cue is the next one.
    const {prompt: _previousPrompt, ...knobs} = handoff.recipe;
    requestBench({source: handoff.source, original: handoff.asset,
        resetHistory: !handoff.keepHistory && !knownVersion, recipe: knobs, prompt: handoff.prompt ?? ''});
    faceHandoff.value = null;
}, {immediate: true});

function helpWithBrief() {
    forgeLead.value = faceSitter.value;
    forgeTarget.value = 'flux';
    forgeIdea.value = facePrompt.value;
    openTab('forge');
}

const brokenBrush = (detail?: FaceJob['detail']) => (detail || [])
    .map((m): BrushFault => (Array.isArray(m) ? m[1] : m) || {})
    .map(d => d.exception_message ? `${d.node_type ? `${d.node_type}: ` : ''}${d.exception_message}` : '')
    .filter(Boolean).join('\n');
let poller: JobPoller | null = null;
let watchGeneration = 0;
onUnmounted(() => { watchGeneration++; poller?.stop(); });
function abandonPainting() {
    watchGeneration++;
    poller?.stop();
    pending.value = null;
    busy.value = false;
    error.value = '';
    persist();
}

function watchPaint(id: string, recipe: FaceRecipe, source: StillAsset | null) {
    busy.value = true;
    poller?.stop();
    const generation = ++watchGeneration;
    poller = createJobPoller({
        fetchJob: async () => {
            const r = await api<FaceJob>(`/api/face/result/${encodeURIComponent(id)}`);
            return {...r, state: r.state === 'painting' ? 'running' : r.state};
        },
        intervalMs: 1500,
        onSettled: r => {
            if (generation !== watchGeneration) return;
            busy.value = false;
            pending.value = null;
            if (r.state === 'done') {
                for (const name of r.images || []) {
                    if (!revisions.value.some(v => v.name === name)) revisions.value.push({name, recipe, source});
                    selected.value = name;
                }
                revisions.value = revisions.value.slice(-40);
                if (!original.value && selected.value) original.value = {room: 'face', name: selected.value};
                void loadArchive().catch(() => {});
            } else if (r.state === 'lost') {
                error.value = 'The Face Shop no longer knows this painting — it is absent from its queue and history. Your earlier versions remain; you can paint again.';
            } else {
                const detail = brokenBrush(r.detail);
                error.value = detail ? `The Face Shop rejected the cue — the broken brush:\n${detail}`
                    : 'The Face Shop rejected the cue — the ComfyUI log names the brush that broke. Your earlier versions remain on the bench.';
            }
        },
        onLost: e => {
            if (generation !== watchGeneration) return;
            busy.value = false;
            error.value = `The booth lost sight of the Face Shop — ${(e as Error)?.message || 'the server stopped answering'}. Reconnect below; the painting may still land in The Canisters.`;
            // Keep the job ID and its exact recipe. Reconnection observes; it never re-fires.
        },
    });
    poller.start();
}
function paintingRequest(r: FaceRecipe) {
    return {prompt: r.prompt, width: r.width, height: r.height, seed: r.seed,
        model: r.model || undefined, source: r.source || undefined};
}
async function cue() {
    if (busy.value || pending.value || transferring.value) return;
    error.value = '';
    if (mode.value === 'refine' && !faceSitter.value) { error.value = 'Choose a character before asking for a change.'; return; }
    busy.value = true;
    const prompt = facePrompt.value.trim() + (changeKeep.value.trim() ? `\nKeep unchanged: ${changeKeep.value.trim()}.` : '');
    const recipe: FaceRecipe = {prompt, seed: Number(seed.value), model: painter.value, width: Number(width.value), height: Number(height.value), source: faceSitter.value};
    const source = sitter.value;
    try {
        const {prompt_id} = await api<{prompt_id: string}>('/api/face/generate', paintingRequest(recipe));
        pending.value = {id: prompt_id, recipe, source};
        persist();
        watchPaint(prompt_id, recipe, source);
    } catch (e) { busy.value = false; error.value = (e as Error).message || String(e); }
}
function reconnect() {
    if (pending.value) watchPaint(pending.value.id, pending.value.recipe, pending.value.source);
}
async function useVersion(asset: StillAsset, recipe: Record<string, unknown> = {}) {
    if (busy.value || transferring.value) return;
    transferring.value = true;
    error.value = '';
    try { await refineStill(asset, recipe, true); }
    catch (e) { error.value = (e as Error).message || String(e); }
    finally { transferring.value = false; }
}
const acts = computed(() => current.value ? [
    {label: transferring.value ? 'Preparing character…' : 'Refine this version →', run: () => useVersion({room: 'face', name: current.value!.name}, {...current.value!.recipe})},
    {label: 'Animate this version →', run: async ({el}: {el: HTMLElement | null}) => {
        try {
            if (busy.value || transferring.value) return;
            await castAsLead(current.value!.name);
            stageTaskHandoff.value = 'i2v';
            const img = el?.querySelector('img');
            if (img?.naturalWidth) leadRes.value = {w: img.naturalWidth, h: img.naturalHeight};
            openTab('stage');
        } catch (e) { error.value = (e as Error).message || String(e); }
    }},
] : []);
const dropBinned = (url: string) => {
    revisions.value = revisions.value.filter(r => stillUrl({room: 'face', name: r.name}) !== url);
    if (!revisions.value.some(r => r.name === selected.value)) selected.value = revisions.value.at(-1)?.name ?? null;
};

async function loadPainters() {
    paintersReady.value = false;
    painterError.value = '';
    try {
        const {painters: list, default: def} = await api<{painters: string[]; default?: string}>('/api/face/models');
        painters.value = list;
        if (!list.includes(painter.value) && def) painter.value = def;
        paintersReady.value = true;
    } catch { painterError.value = 'The painter roster is unavailable. Your character and cue are ready; retry the list before choosing a painter.'; }
}
onMounted(async () => {
    // A pending painting can be observed even if the painter roster is dark.
    if (pending.value) reconnect();
    await loadPainters();
});
</script>

<template>
  <RoomFlow room="face" :current="progress" />
  <div class="panel face-workbench">
    <div class="face-controls">
    <section id="face-source">
      <h3 class="flow-heading">1 · Choose where this version begins</h3>
      <div class="task-picks">
        <button :aria-pressed="mode === 'refine'" :disabled="busy || !!pending || transferring" @click="chooseMode('refine')">Refine a character</button>
        <button :aria-pressed="mode === 'create'" :disabled="busy || !!pending || transferring" @click="chooseMode('create')">Create a new still</button>
      </div>
      <template v-if="mode === 'refine'">
        <figure v-if="sitter" class="character-source"><img :src="stillUrl(sitter)" alt="The character chosen for this change"><figcaption>{{ sitter.name }}</figcaption></figure>
        <label class="field">Choose a still, bring your own, or refine a painting from The Canisters</label>
        <ThumbRow id="face-thumbs" :picked="faceSitter" @pick="pickSitter" />
      </template>
    </section>
    <h3 class="flow-heading">2 · {{ mode === 'refine' ? 'Describe the change' : 'Describe the still' }}</h3>
    <label class="field" for="face-prompt">{{ mode === 'refine' ? 'What should change?' : 'The cue' }}</label>
    <Textarea id="face-prompt" v-model="facePrompt" :placeholder="mode === 'refine' ? 'Make her grin sharper; keep her pose and costume…' : 'Describe the character, pose and setting…'" />
    <template v-if="mode === 'refine'">
      <label class="field" for="face-keep">What should stay the same? · optional guidance; check the result</label>
      <Textarea id="face-keep" v-model="changeKeep" placeholder="Hair, clothes, silhouette, camera angle…" />
    </template>
    <button class="act brief-help" @click="helpWithBrief">Help write this cue in the Forge →</button>
    <details class="room-settings">
      <summary>Advanced settings · painter, dimensions and seed</summary>
      <label class="field" for="face-model">The painter</label>
      <SingleSelect id="face-model" v-model="painter" :options="painterOptions" :label="(option: {label: string}) => option.label" :alphabetical-sort="false" options-label="The painters in the storeroom" />
      <div class="row" style="margin-top:14px">
        <div><label class="field" for="face-w">Width</label><NumberInput id="face-w" v-model="width" :step="16" :disabled="!!faceSitter" /></div>
        <div><label class="field" for="face-h">Height</label><NumberInput id="face-h" v-model="height" :step="16" :disabled="!!faceSitter" /></div>
        <div><label class="field" for="face-seed">Seed</label><NumberInput id="face-seed" v-model="seed" /></div>
      </div>
      <p class="note">Refinements follow the source dimensions. A fixed seed helps compare changes; it cannot guarantee that the character stays identical.</p>
    </details>
    <p v-if="formulaNote" class="note">{{ formulaNote }}</p>
    <p v-if="painterError" class="note">{{ painterError }} <button class="act" @click="loadPainters">Retry painter list</button></p>
    <h3 class="flow-heading">3 · Call the painter</h3>
    <button id="face-go" class="fire" :disabled="busy || !!pending || transferring" @click="cue">{{ busy ? 'Painting…' : mode === 'refine' ? 'Paint this change' : 'Paint the still' }}</button>
    <div v-if="pending" class="note pending-painting">
      <p v-if="!busy">A painting is awaiting reconnection. <button class="act" @click="reconnect">Reconnect to the painting</button></p>
      <button id="face-abandon" class="act" @click="abandonPainting">Abandon this painting</button>
      <p>This releases the bench and keeps your versions. A painting still running may finish in The Canisters.</p>
    </div>
    <p v-if="faceHandoff && pending" class="note">Another character is waiting for this bench. Finish or abandon the current painting before choosing it.</p>
    <p v-show="error" class="error" role="alert">{{ error }}</p>
    </div>
    <div class="face-output">
    <section id="face-compare">
      <h3 class="flow-heading">4 · Compare the character</h3>
      <div v-if="current" class="task-picks">
        <button :aria-pressed="comparison === 'source'" @click="comparison = 'source'">Compare with this take's source</button>
        <button :aria-pressed="comparison === 'original'" @click="comparison = 'original'">Compare with the original</button>
      </div>
      <div id="face-result" class="face-comparison">
        <figure v-if="compareAsset" class="comparison-reference">
          <figcaption>{{ comparison === 'original' ? 'Original character' : 'Source for this take' }}</figcaption>
          <img :src="stillUrl(compareAsset)" :alt="comparison === 'original' ? 'Original character' : 'Source for this take'">
        </figure>
        <StampedMount v-if="current" :key="current.name" room="face" :url="currentUrl" kind="image" :title="current.recipe.prompt"
          :stamp="`Version ${revisions.findIndex(r => r.name === current!.name) + 1}`"
          :meta="{model: current.recipe.model.replace(/\.(gguf|safetensors)$/i, ''), seed: current.recipe.seed}" :acts="acts" @binned="dropBinned" />
        <p v-else class="empty">{{ busy ? 'The painter is at work. Earlier versions stay on the bench.' : 'The next painting will hang beside its source here.' }}</p>
      </div>
    </section>
    <section id="face-revisions">
      <h3 class="flow-heading">5 · Choose the next version</h3>
      <div class="revision-strip">
        <button v-if="original" class="revision original" :disabled="busy || transferring" @click="useVersion(original)"><img :src="stillUrl(original)" alt="Original character"><span>Refine the original</span></button>
        <button v-for="(r, i) in revisions" :key="r.name" class="revision" :aria-pressed="selected === r.name" @click="selected = r.name">
          <img :src="stillUrl({room: 'face', name: r.name})" :alt="`Version ${i + 1}`"><span>Version {{ i + 1 }}</span>
        </button>
      </div>
      <p class="note">Choose any version to compare, refine, download or animate. The latest 40 versions and the current cue survive a browser refresh; every painting also lives in The Canisters.</p>
    </section>
    </div>
  </div>
  <dialog ref="resetDialog" class="take-bin" @cancel="cancelNewBench">
    <h2>Start a new character bench?</h2>
    <p>This clears the working versions and their recipes from this bench. The paintings remain in The Canisters.</p>
    <div class="acts">
      <button class="act" @click="cancelNewBench">Keep this character</button>
      <button id="face-new-confirm" class="fire" @click="confirmNewBench">Start new bench</button>
    </div>
  </dialog>
</template>

<style>
.face-workbench { display: grid; grid-template-columns: minmax(300px, .8fr) minmax(0, 1.2fr); gap: 28px; align-items: start; }
.face-controls, .face-output { min-width: 0; }
.face-output { position: sticky; top: 0; }
.face-output .flow-heading:first-child { margin-top: 0; }
.face-workbench .flow-heading:first-child { margin-top: 0; }
.character-source { margin: 0 0 16px; display: flex; align-items: center; gap: 16px; }
.character-source img { width: 110px; height: 145px; object-fit: contain; background: #17130f; }
.character-source figcaption { font: 11px var(--typed); color: var(--ink-soft); overflow-wrap: anywhere; }
.brief-help { margin-top: 10px; }
.face-comparison { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; align-items: start; }
.comparison-reference { position: relative; margin: 0; background: #17130f; }
.comparison-reference figcaption { position: absolute; top: 0; left: 0; font: 11px var(--typed); color: var(--ink-soft); padding: 8px 10px; background: var(--page-shade); }
.comparison-reference img, .face-comparison .mount-frame img { display: block; width: 100%; height: min(36vh, 440px); max-height: none; object-fit: contain; background: #17130f; }
.face-comparison .mount { box-shadow: 0 2px 8px rgba(0,0,0,.15); }
.revision-strip { display: flex; gap: 10px; overflow-x: auto; padding: 4px 0 12px; }
.revision { flex: 0 0 100px; border: 1px solid var(--ink-hair); background: var(--page); color: var(--ink-soft); padding: 5px; cursor: pointer; font: 10px var(--typed); }
.revision img { display: block; width: 100%; height: 110px; object-fit: contain; background: #17130f; margin-bottom: 7px; }
.revision[aria-pressed="true"] { border: 2px solid var(--ink); color: var(--ink); }
.revision:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
@media (max-width: 1180px) { .face-workbench { grid-template-columns: minmax(0, 1fr); } .face-output { position: static; } }
@media (max-width: 1000px) { .face-comparison { grid-template-columns: minmax(0, 1fr); } }
</style>
