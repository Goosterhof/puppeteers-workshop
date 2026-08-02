<script setup lang="ts">
import {TextInput} from '@script-development/ui-inputs';
import {computed, nextTick, ref, watch} from 'vue';
import CanisterCard from '../components/CanisterCard.vue';
import FilterPills from '../components/FilterPills.vue';
import StampedMount from '../components/StampedMount.vue';
import type {MountAct} from '../components/StampedMount.vue';
import {age, filterArchive, ROOMS} from '../lib/canisters';
import type {ShelfItem} from '../lib/canisters';
import {archive, loadArchive} from '../stores/archive';
import {castAsLead, leadRes, loadFoleySources, openTab} from '../stores/booth';

const props = withDefaults(defineProps<{active?: boolean}>(), {active: false});

const search = ref('');
const room = ref('');
const kind = ref('');
const mounted = ref<ShelfItem | null>(null);
const acts = ref<MountAct[]>([]);
const view = ref<HTMLElement | null>(null);

const items = computed(() => filterArchive(archive.value, {room: room.value, kind: kind.value, search: search.value}));
const filtered = computed(() => Boolean(room.value || kind.value || search.value.trim()));
const countLine = computed(() => items.value.length
    ? `${items.value.length} canister${items.value.length === 1 ? '' : 's'} on the shelf${filtered.value ? ' — filtered' : ''}. Click one to mount it.`
    : filtered.value ? 'No canister answers that description — loosen a filter.'
    : 'The shelves are bare — nothing developed yet. Every Stage take, painting, and score lands here on its own.');

// The archive mount is a Print like every fresh take (#00085 detonation 3):
// same paper, same chips — the age stamp sits where Fresh sits.
const mountedSrc = computed(() => mounted.value
    ? ROOMS[mounted.value.room].src + encodeURIComponent(mounted.value.name) : '');
const mountedTitle = computed(() => !mounted.value ? ''
    : mounted.value.meta?.prompt ? `“${mounted.value.meta.prompt}” — ${mounted.value.name}`
    : mounted.value.name);

function buildActs(it: ShelfItem): MountAct[] {
    const rows: MountAct[] = [];
    if (it.meta?.prompt) {
        rows.push({label: 'Copy the cue', run: ctx => {
            navigator.clipboard.writeText(it.meta!.prompt!);
            ctx.relabel('Cue copied');
        }});
    }
    if (it.room === 'stage' && it.kind === 'video') {
        rows.push({label: 'Score it in the foley booth →', run: async () => {
            await loadFoleySources(`stage:${it.name}`);
            openTab('foley');
        }});
    }
    if (it.room === 'stage' && it.kind === 'image') {
        rows.push({label: 'Cast as a lead →', run: async ctx => {
            await castAsLead(it.name, 'stage');
            ctx.relabel('Cast — it is in the footage now');
        }});
    }
    if (it.room === 'face') {
        rows.push({label: 'Send to the stage →', run: async ctx => {
            await castAsLead(it.name);
            const img = ctx.el?.querySelector('img');
            if (img?.naturalWidth) leadRes.value = {w: img.naturalWidth, h: img.naturalHeight};
            openTab('stage');
        }});
    }
    return rows;
}

async function mountCanister(it: ShelfItem) {
    mounted.value = it;
    acts.value = buildActs(it);
    await nextTick();
    view.value?.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}

// fresh shelves on entry, same as the old tab hook — and once at first light
watch(() => props.active, a => {
    if (a) loadArchive();
}, {immediate: true});
</script>

<template>
  <div class="panel">
    <div class="row">
      <div style="flex:2;min-width:220px">
        <label class="field" for="arch-search">Search the shelves — filename, prompt slug, seed</label>
        <TextInput id="arch-search" v-model="search" placeholder="seed7, crier, flask…" />
      </div>
      <div>
        <label class="field">Room</label>
        <FilterPills
          v-model="room"
          :options="[{value: '', label: 'All'}, {value: 'stage', label: 'Stage'},
                     {value: 'face', label: 'Face Shop'}, {value: 'foley', label: 'Foley'}]"
        />
      </div>
      <div>
        <label class="field">Kind</label>
        <FilterPills
          v-model="kind"
          :options="[{value: '', label: 'All'}, {value: 'video', label: 'Reels'},
                     {value: 'image', label: 'Stills'}, {value: 'audio', label: 'Audio'}]"
        />
      </div>
    </div>
    <p id="arch-count" class="note">{{ countLine }}</p>
    <div id="arch-view" ref="view" class="result">
      <StampedMount
        v-if="mounted"
        :key="`${mounted.room}/${mounted.name}`"
        :room="mounted.room" :url="mountedSrc" :kind="mounted.kind || 'video'"
        :title="mountedTitle" :meta="mounted.meta" :stamp="age(mounted.mtime)" :acts="acts"
      />
    </div>
    <!-- the thumbrow class rides along like the old markup — its 2px transparent
         border and .75 opacity on card images are part of the booth's look -->
    <div id="arch-grid" class="thumbrow" style="margin-top:16px">
      <CanisterCard v-for="it in items" :key="`${it.room}/${it.name}`" :item="it" @mount="mountCanister" />
    </div>
  </div>
</template>

<style>
#arch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 14px; margin-top: 16px; }
</style>
