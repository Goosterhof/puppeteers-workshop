<script setup lang="ts">
import {nextTick, onUnmounted, reactive, ref, watch} from 'vue';
import BreakPit from '../components/BreakPit.vue';
import RackCard from '../components/RackCard.vue';
import type {Firing} from '../components/RackCard.vue';
import {api} from '../composables/useBoothApi';

const props = withDefaults(defineProps<{active?: boolean}>(), {active: false});

const pending = ref<Firing[]>([]);
const spotId = ref<string | null>(null);
const spinFrame = ref(0);
const error = ref('');
const cardErrors = reactive<Record<string, string>>({});
const seenScars = new Set<string>(); // candidates whose ember scar already flared
const mendedIds = ref(new Set<string>());
const view = ref<HTMLElement | null>(null);
const breakPit = ref<{open: (entry: Firing) => void} | null>(null);

const REDUCED_MOTION = matchMedia('(prefers-reduced-motion: reduce)');
let spinTimer: ReturnType<typeof setInterval> | undefined;

// a slow shelf turn — 4 s the way round; the Wheel is where you go fast
function startSpin() {
    clearInterval(spinTimer);
    if (!pending.value.some(e => e.frames?.length)) return;
    if (REDUCED_MOTION.matches) {
        spinFrame.value = 0; // freeze on angle 0
        return;
    }
    spinTimer = setInterval(() => {
        spinFrame.value = (spinFrame.value + 1) % 8;
    }, 500);
}
REDUCED_MOTION.addEventListener('change', startSpin);
onUnmounted(() => {
    clearInterval(spinTimer);
    REDUCED_MOTION.removeEventListener('change', startSpin);
});

async function loadRack() {
    error.value = '';
    try {
        pending.value = ((await api<{candidates?: Firing[]}>('/api/rack/list')).candidates || [])
            .filter(c => c.recipe.status === 'pending');
        // the Mend: a refired candidate's scar flares once, the first time it deals in
        const fresh = new Set<string>();
        for (const e of pending.value) {
            if (e.recipe.refire_count > 0 && !seenScars.has(e.id)) {
                fresh.add(e.id);
                seenScars.add(e.id);
            }
        }
        mendedIds.value = fresh;
        if (spotId.value && !pending.value.some(e => e.id === spotId.value)) spotId.value = null;
        startSpin();
    } catch (e) {
        error.value = (e as Error).message || String(e);
    }
}

async function spotlight(id: string) {
    spotId.value = id === spotId.value ? null : id;
    if (spotId.value) {
        await nextTick();
        view.value?.scrollIntoView({behavior: REDUCED_MOTION.matches ? 'auto' : 'smooth', block: 'nearest'});
    }
}

async function breakFiring(entry: Firing) {
    try {
        await api('/api/rack/discard', {candidate_id: entry.id});
        loadRack();
    } catch (e) {
        cardErrors[entry.id] = (e as Error).message;
    }
}

watch(() => props.active, a => {
    if (a) loadRack(); // fresh candidates on entry
}, {immediate: true});
</script>

<template>
  <div class="panel">
    <p class="note">Every fired candidate waits here for a verdict. Click a piece to put it
      on the Potter's Wheel — only the piece on the wheel turns in your hand. Three verdicts:
      <b>Approve</b> shelves the pair on the Prop Shelf, <b>Refire</b> re-meshes the SAME
      painting at a new octree, <b>Discard</b> breaks the firing for good — behind a confirm,
      because shards don't come back. Nothing ships without a thumb on Approve.</p>
    <p v-show="error" class="error">{{ error }}</p>
    <div id="rack-view" ref="view" class="result">
      <RackCard
        v-for="entry in pending.filter(e => e.id === spotId)" :key="`spot-${entry.id}`"
        :entry="entry" :on-wheel="true" :spin-frame="spinFrame"
        :outer-error="cardErrors[entry.id] || ''"
        @spotlight="spotlight(entry.id)" @reload="loadRack" @discard="breakPit?.open($event)"
      />
    </div>
    <div id="rack-grid">
      <p v-if="!pending.length" class="empty">Nothing curing right now — fire a prop or brief the Night Shift.</p>
      <RackCard
        v-for="entry in pending" :key="entry.id"
        :entry="entry" :spin-frame="spinFrame"
        :mended="mendedIds.has(entry.id)" :spotlit="entry.id === spotId"
        :outer-error="cardErrors[entry.id] || ''"
        @spotlight="spotlight(entry.id)" @reload="loadRack" @discard="breakPit?.open($event)"
      />
    </div>
    <BreakPit ref="breakPit" @break="breakFiring" />
  </div>
</template>

<style>
#rack-grid, #shelf-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
             gap: 14px; margin-top: 16px; }
#rack-view:empty, #shelf-view:empty { display: none; }
</style>
