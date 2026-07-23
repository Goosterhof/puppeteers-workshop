<script setup lang="ts">
import {NumberInput, SingleSelect, TextInput, Textarea} from '@script-development/ui-inputs';
import {computed, onMounted, onUnmounted, ref} from 'vue';
import LogWell from '../components/LogWell.vue';
import StampedMount from '../components/StampedMount.vue';
import {api} from '../composables/useBoothApi';
import {createJobPoller} from '../composables/useJobPoller';
import {loadArchive} from '../stores/archive';
import {foleyReel, foleySources, loadFoleySources} from '../stores/booth';

interface FoleyJob {
    state?: string;
    seed?: number;
    outputs?: string[];
    exit_code?: number;
    log_tail?: string[];
}

interface FoleyTake {
    url: string;
    kind: string;
    title: string;
    meta: {seed?: number};
}

const prompt = ref('');
const negative = ref('music, background music, melody');
// no-reel rides as a real option (id '') — a picked reel must stay clearable,
// exactly like the old empty <option>
const reelOptions = computed(() => [
    {id: '', label: '— no reel: pure text-to-audio —'},
    ...foleySources.value.stage.map(n => ({id: `stage:${n}`, label: `stage · ${n}`})),
    ...foleySources.value.footage.map(n => ({id: `footage:${n}`, label: `footage · ${n}`})),
]);
const duration = ref(8);
const seed = ref(7);
const error = ref('');
const logLines = ref<string[]>([]);
const logShown = ref(false);
const results = ref<FoleyTake[] | null>(null); // null = nothing cued yet — the empty note stands

function settle(job: FoleyJob) {
    if (job.state === 'done') {
        loadArchive();
        results.value = (job.outputs || []).map(f => ({
            url: `/foley-output/${encodeURIComponent(f)}`,
            kind: f.endsWith('.mp4') ? 'video' : 'audio',
            title: f.endsWith('.mp4') ? `${f} — the composite: sound on the frames` : f,
            meta: {seed: job.seed},
        }));
    } else if (job.state === 'failed') {
        error.value = `The score collapsed (exit ${job.exit_code}). The log above names the broken instrument — first cold run downloads the weights, give that one time.`;
    }
}

const poller = createJobPoller({
    fetchJob: () => api<FoleyJob>('/api/foley/job'),
    intervalMs: 3000,
    onTick: job => {
        logLines.value = job.log_tail || [];
    },
    onSettled: settle,
    onLost: () => {
        error.value = 'The booth lost sight of the foley booth — the server stopped answering. Reload to reconnect; the score may still be recording.';
    },
});

async function cue() {
    error.value = '';
    const [from, ...rest] = (foleyReel.value || ':').split(':');
    try {
        await api('/api/foley/generate', {
            prompt: prompt.value, negative_prompt: negative.value,
            duration: Number(duration.value), seed: Number(seed.value),
            video: rest.join(':'), video_from: from || undefined,
        });
        results.value = [];
        logShown.value = true;
        poller.start();
    } catch (e) {
        error.value = (e as Error).message || String(e);
    }
}

onMounted(async () => {
    loadFoleySources().catch(() => {});
    // resume watching if a score is already recording when the room opens
    try {
        const job = await api<FoleyJob>('/api/foley/job');
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
    <label class="field" for="foley-prompt">The cue — what should it sound like</label>
    <Textarea id="foley-prompt" v-model="prompt" placeholder="a man screams in terror as he falls, classic movie stock scream" />
    <label class="field" for="foley-video">The reel — optional: score a video (audio lands ON the motion)</label>
    <SingleSelect
      id="foley-video" v-model="foleyReel"
      :options="reelOptions" label="label" :alphabetical-sort="false"
      options-label="The reels — stage takes, then footage"
    />
    <div class="row" style="margin-top:14px">
      <div><label class="field" for="foley-neg">Negative cue</label><TextInput id="foley-neg" v-model="negative" /></div>
      <div><label class="field" for="foley-dur">Seconds</label><NumberInput id="foley-dur" v-model="duration" :min="1" :max="30" :step="1" /></div>
      <div><label class="field" for="foley-seed">Seed</label><NumberInput id="foley-seed" v-model="seed" /></div>
      <div><button id="foley-go" class="fire" style="margin-top:0" @click="cue">Cue the foley booth</button></div>
    </div>
    <p class="note">MMAudio (T2A + V2A) — with a reel picked, the sync module watches the frames and the duration snaps to the clip; without one, 8&nbsp;s is the trained sweet spot (trim the sting after). The "music" negative cue earns its seat — the model loves to score things unasked. ~6&nbsp;GB VRAM; weights CC-BY-NC — internal tooling only (runbook).</p>
    <p v-show="error" class="error">{{ error }}</p>
    <LogWell :lines="logLines" :shown="logShown" />
    <div id="foley-result" class="result">
      <p v-if="results === null" class="empty">No score yet — cue the foley booth and it plays here.</p>
      <StampedMount
        v-for="r in results || []" :key="r.url"
        room="foley" :url="r.url" :kind="r.kind" :title="r.title" :meta="r.meta"
      />
    </div>
  </div>
</template>
