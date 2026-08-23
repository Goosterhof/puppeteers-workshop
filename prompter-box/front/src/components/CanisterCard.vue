<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, ref} from 'vue';
import type {ShelfItem} from '../lib/canisters';
import {ROOMS} from '../lib/canisters';

const props = defineProps<{item: ShelfItem; onBench?: boolean}>();
const emit = defineEmits<{mount: [item: ShelfItem]}>();

const src = computed(() => ROOMS[props.item.room].src + encodeURIComponent(props.item.name));
const label = computed(() => props.item.meta?.prompt || props.item.name);
const roomLabel = computed(() => ROOMS[props.item.room].label);

// The Light Table re-cut (2026-08-23): the shelf shows pictures, not
// manifests. Frame, one line of title, the room chip — every other chip now
// lives on the print, which the bench keeps in view at all times. Repeating
// the whole strip on 193 cards is what made the shelf 12,000px tall.
//
// A reel shows its poster frame only once the browser has read its metadata,
// and 193 metadata requests on every entry is the second cost the audit
// named. So a card off the shelf's edge asks for nothing at all; it upgrades
// to `metadata` the moment it comes near the viewport, and never goes back.
const el = ref<HTMLElement | null>(null);
const near = ref(false);
let watcher: IntersectionObserver | undefined;
onMounted(() => {
    if (props.item.kind !== 'video') return;
    if (typeof IntersectionObserver === 'undefined' || !el.value) {
        near.value = true; // no observer to lean on — fall back to the old eager poster
        return;
    }
    watcher = new IntersectionObserver(entries => {
        if (!entries.some(e => e.isIntersecting)) return;
        near.value = true;
        watcher?.disconnect();
    }, {rootMargin: '400px'});
    watcher.observe(el.value);
});
onBeforeUnmount(() => watcher?.disconnect());
</script>

<template>
  <button
    ref="el" class="canister" :data-canister="`${item.room}/${item.name}`" :title="item.name"
    :aria-current="onBench ? 'true' : undefined" @click="emit('mount', item)"
  >
    <div class="frame">
      <img v-if="item.kind === 'image'" :src="src" loading="lazy" :alt="item.name">
      <video v-else-if="item.kind === 'video'" :src="near ? src : undefined" muted :preload="near ? 'metadata' : 'none'"></video>
      <template v-else>♪</template>
    </div>
    <div class="body">
      <div class="title">{{ label }}</div>
      <div class="chips"><span class="chip room">{{ roomLabel }}</span></div>
    </div>
  </button>
</template>

<style>
.canister {
  background: var(--booth); border: 1px solid var(--drape-edge); border-radius: 3px;
  overflow: hidden; cursor: pointer; text-align: left; padding: 0;
  /* the browser's own virtual scrolling, at the cost of two declarations:
     off-screen cards skip layout and paint entirely. The intrinsic size is a
     MEASURED card (see the runbook), not a guess — a wrong number makes the
     scrollbar jump as cards are realised. */
  content-visibility: auto;
  contain-intrinsic-size: 0 129px;
}
.canister:hover { border-color: var(--lamp-dim); }
/* the one on the bench keeps its place in the eye: 2px of INK, never lamp —
   --filament/--lamp on cream is the 1.15:1 sin the dog-ear repair paid for once */
.canister[aria-current="true"] { border-color: var(--ink); box-shadow: 0 0 0 2px var(--ink); }
.canister .frame {
  aspect-ratio: 16 / 9; background: #0d0b08; display: flex; align-items: center; justify-content: center;
  color: var(--lamp-dim); font-size: 26px;
}
.canister .frame img, .canister .frame video { width: 100%; height: 100%; object-fit: cover; display: block; }
.canister .body { padding: 8px 10px 10px; }
.canister .title {
  font: 12px var(--typed); color: var(--paper); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden;
}
.canister .chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.canister .chip {
  font: 10px var(--display); letter-spacing: .12em; text-transform: uppercase;
  border: 1px solid var(--drape-edge); color: var(--dim); padding: 2px 6px; border-radius: 2px;
}
.canister .chip.room { color: var(--lamp-dim); border-color: var(--lamp-dim); }
</style>
