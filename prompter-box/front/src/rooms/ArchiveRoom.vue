<script setup lang="ts">
import {TextInput} from '@script-development/ui-inputs';
import {computed, nextTick, ref, watch} from 'vue';
import CanisterCard from '../components/CanisterCard.vue';
import FilterPills from '../components/FilterPills.vue';
import {canisterChips, filterArchive, ROOMS} from '../lib/canisters';
import type {ShelfItem} from '../lib/canisters';
import {archive, loadArchive} from '../stores/archive';
import {castAsLead, leadRes, loadFoleySources, openTab} from '../stores/booth';

const props = withDefaults(defineProps<{active?: boolean}>(), {active: false});

interface ShelfAct {
    label: string;
    run: (act: ShelfAct) => void | Promise<void>;
}

const search = ref('');
const room = ref('');
const kind = ref('');
const mounted = ref<ShelfItem | null>(null);
const acts = ref<ShelfAct[]>([]);
const view = ref<HTMLElement | null>(null);

const items = computed(() => filterArchive(archive.value, {room: room.value, kind: kind.value, search: search.value}));
const filtered = computed(() => Boolean(room.value || kind.value || search.value.trim()));
const countLine = computed(() => items.value.length
    ? `${items.value.length} canister${items.value.length === 1 ? '' : 's'} on the shelf${filtered.value ? ' — filtered' : ''}. Click one to mount it.`
    : filtered.value ? 'No canister answers that description — loosen a filter.'
    : 'The shelves are bare — nothing developed yet. Every Stage take, painting, and score lands here on its own.');

const mountedSrc = computed(() => mounted.value
    ? ROOMS[mounted.value.room].src + encodeURIComponent(mounted.value.name) : '');
const capText = computed(() => {
    if (!mounted.value) return '';
    const it = mounted.value;
    const label = canisterChips(it).map(([text]) => text).join(' · ');
    const cue = it.meta?.prompt ? `“${it.meta.prompt}” — ` : '';
    return `${cue}${it.name} · ${label} `;
});

function buildActs(it: ShelfItem): ShelfAct[] {
    const rows: ShelfAct[] = [];
    if (it.meta?.prompt) {
        rows.push({label: 'Copy the cue', run: act => {
            navigator.clipboard.writeText(it.meta!.prompt!);
            act.label = 'Cue copied';
        }});
    }
    if (it.room === 'stage' && it.kind === 'video') {
        rows.push({label: 'Score it in the foley booth →', run: async () => {
            await loadFoleySources(`stage:${it.name}`);
            openTab('foley');
        }});
    }
    if (it.room === 'stage' && it.kind === 'image') {
        rows.push({label: 'Cast as a lead →', run: async act => {
            await castAsLead(it.name, 'stage');
            act.label = 'Cast — it is in the footage now';
        }});
    }
    if (it.room === 'face') {
        rows.push({label: 'Send to the stage →', run: async () => {
            await castAsLead(it.name);
            const img = view.value?.querySelector('img');
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
      <template v-if="mounted">
        <img v-if="mounted.kind === 'image'" :src="mountedSrc" :alt="mounted.name">
        <video v-else-if="mounted.kind === 'video'" :src="mountedSrc" controls loop></video>
        <audio v-else :src="mountedSrc" controls></audio>
        <span class="cap">{{ capText }}
          <button v-for="(act, i) in acts" :key="i" class="cast" @click="act.run(act)">{{ act.label }}</button>
        </span>
      </template>
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
#arch-view video, #arch-view img { max-width: 100%; max-height: 65vh; border-radius: 3px; box-shadow: 0 4px 18px rgba(0,0,0,.5); }
.cast {
  background: none; border: 1px solid var(--drape-edge); color: var(--dim);
  font: 11px var(--display); letter-spacing: .16em; text-transform: uppercase;
  padding: 5px 11px; cursor: pointer; border-radius: 2px; margin-left: 10px;
}
.cast:hover { border-color: var(--lamp); color: var(--lamp); }
</style>
