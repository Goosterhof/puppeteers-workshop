<script setup lang="ts">
import {nextTick, ref, watch} from 'vue';
import PottersWheel from '../components/PottersWheel.vue';
import {api} from '../composables/useBoothApi';

interface ShelfProp {
    name: string;
    glb: string;
    hide?: string;
    glb_mb: number;
    octree?: number;
    seed?: number | null;
    two_sided?: boolean;
    subject?: string;
}

const props = withDefaults(defineProps<{active?: boolean}>(), {active: false});

const shelf = ref<ShelfProp[]>([]);
const spotName = ref<string | null>(null);
const error = ref('');
const view = ref<HTMLElement | null>(null);

async function loadShelf() {
    error.value = '';
    try {
        shelf.value = (await api<{props?: ShelfProp[]}>('/api/shelf/list')).props || [];
        if (spotName.value && !shelf.value.some(p => p.name === spotName.value)) spotName.value = null;
    } catch (e) {
        error.value = (e as Error).message || String(e);
    }
}

async function spotlight(name: string) {
    spotName.value = name === spotName.value ? null : name;
    if (spotName.value) {
        await nextTick();
        const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
        view.value?.scrollIntoView({behavior: reduced ? 'auto' : 'smooth', block: 'nearest'});
    }
}

const chips = (prop: ShelfProp): string[] => {
    const rows = [`${prop.glb_mb} MB`];
    if (prop.octree) rows.push(`octree ${prop.octree}`);
    if (prop.seed !== null && prop.seed !== undefined) rows.push(`seed ${prop.seed}`);
    if (prop.two_sided) rows.push('two-sided');
    return rows;
};

watch(() => props.active, a => {
    if (a) loadShelf(); // fresh props on entry
}, {immediate: true});
</script>

<template>
  <div class="panel">
    <p class="note">Every approved firing lives here — the Workshop's own prop library,
      mesh and painting side by side. Consumers come to the shelf, not the other way
      around: the town sketches pack from it with
      <code>node pack-props.mjs ~/code/video-lab/prompter-box/pack-queue</code>, and
      whatever the lab builds next reads the same shelf. Click a prop to put it on the
      Potter's Wheel.</p>
    <p v-show="error" class="error">{{ error }}</p>
    <div id="shelf-view" ref="view" class="result">
      <article
        v-for="prop in shelf.filter(p => p.name === spotName)" :key="`spot-${prop.name}`"
        class="canister candidate spotlight" :data-name="prop.name"
      >
        <PottersWheel
          class="well"
          :glb-url="`/pack-queue/${prop.glb}`"
          :poster-src="prop.hide ? `/pack-queue/${prop.hide}` : ''"
          :poster-alt="prop.name"
        />
        <div class="body">
          <p class="title">{{ prop.name }}</p>
          <div class="chips"><span v-for="c in chips(prop)" :key="c" class="chip">{{ c }}</span></div>
          <p v-if="prop.subject" class="qa-line">{{ prop.subject }}</p>
          <div class="acts">
            <button class="act" @click="spotlight(prop.name)">✕ Off the wheel</button>
          </div>
        </div>
      </article>
    </div>
    <div id="shelf-grid">
      <p v-if="!shelf.length" class="empty">The shelf is bare — Approve a firing on the Curing Rack and it lands here.</p>
      <article
        v-for="prop in shelf" :key="prop.name"
        class="canister candidate" :class="{spotlit: prop.name === spotName}" :data-name="prop.name"
      >
        <div
          class="well shelf" title="Put it on the Potter's Wheel"
          @click="spotlight(prop.name)"
        >
          <img v-if="prop.hide" class="still" :src="`/pack-queue/${prop.hide}`" :alt="prop.name">
        </div>
        <div class="body">
          <p class="title">{{ prop.name }}</p>
          <div class="chips"><span v-for="c in chips(prop)" :key="c" class="chip">{{ c }}</span></div>
          <p v-if="prop.subject" class="qa-line">{{ prop.subject }}</p>
        </div>
      </article>
    </div>
  </div>
</template>
