<script setup lang="ts">
import {computed} from 'vue';
import type {ShelfItem} from '../lib/canisters';
import {canisterChips, ROOMS} from '../lib/canisters';

const props = defineProps<{item: ShelfItem}>();
const emit = defineEmits<{mount: [item: ShelfItem]}>();

const src = computed(() => ROOMS[props.item.room].src + encodeURIComponent(props.item.name));
const chips = computed(() => canisterChips(props.item));
</script>

<template>
  <button class="canister" :title="item.name" @click="emit('mount', item)">
    <div class="frame">
      <img v-if="item.kind === 'image'" :src="src" loading="lazy" :alt="item.name">
      <video v-else-if="item.kind === 'video'" :src="src" muted preload="metadata"></video>
      <template v-else>♪</template>
    </div>
    <div class="body">
      <div class="title">{{ item.meta?.prompt || item.name }}</div>
      <div class="chips">
        <span v-for="([text, cls], i) in chips" :key="i" :class="cls">{{ text }}</span>
      </div>
    </div>
  </button>
</template>

<style>
.canister {
  background: var(--booth); border: 1px solid var(--drape-edge); border-radius: 3px;
  overflow: hidden; cursor: pointer; text-align: left; padding: 0;
}
.canister:hover { border-color: var(--lamp-dim); }
.canister .frame {
  height: 148px; background: #0d0b08; display: flex; align-items: center; justify-content: center;
  color: var(--lamp-dim); font-size: 34px;
}
.canister .frame img, .canister .frame video { width: 100%; height: 148px; object-fit: cover; display: block; }
.canister .body { padding: 10px 12px 12px; }
.canister .title {
  font: 12.5px var(--typed); color: var(--paper); line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.canister .chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.canister .chip {
  font: 10px var(--display); letter-spacing: .12em; text-transform: uppercase;
  border: 1px solid var(--drape-edge); color: var(--dim); padding: 2px 6px; border-radius: 2px;
}
.canister .chip.room { color: var(--lamp-dim); border-color: var(--lamp-dim); }
</style>
