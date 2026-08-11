<script setup lang="ts">
import {computed} from 'vue';
import type {PinnedRecipe} from '../lib/pins';
import {applyLabel as pinApplyLabel, recipeChips} from '../lib/pins';
import {ROOMS} from '../lib/canisters';

// One named formula hanging on the Pinboard — room chip, knob chips, the
// prompt as an underline when the formula carries one, and two acts:
// replay it in its room, or take it down.
const props = defineProps<{pin: PinnedRecipe}>();
const emit = defineEmits<{apply: [pin: PinnedRecipe]; unpin: [pin: PinnedRecipe]}>();

const roomLabel = computed(() => (props.pin.room === 'kiln' ? 'Kiln' : ROOMS[props.pin.room].label));
const chips = computed(() => recipeChips(props.pin.recipe));
const applyLabel = computed(() => pinApplyLabel(props.pin));
const promptLine = computed(() => (typeof props.pin.recipe.prompt === 'string' ? props.pin.recipe.prompt : ''));
</script>

<template>
  <article class="pin-card" :data-room="pin.room">
    <p class="pin-name"><span class="pin-tack" aria-hidden="true">◉</span>{{ pin.name }}</p>
    <div class="chips">
      <span class="chip room">{{ roomLabel }}</span>
      <span v-for="([text, cls], i) in chips" :key="i" :class="cls">{{ text }}</span>
    </div>
    <p v-if="promptLine" class="pin-prompt" :title="promptLine">“{{ promptLine }}”</p>
    <div class="pin-acts">
      <button v-if="applyLabel" class="act" @click="emit('apply', pin)">{{ applyLabel }}</button>
      <button class="act unpin" @click="emit('unpin', pin)">Unpin</button>
    </div>
  </article>
</template>

<style>
.pin-card {
  background: var(--booth); border: 1px solid var(--drape-edge); border-radius: 3px;
  padding: 12px 14px 13px; text-align: left;
}
.pin-card:hover { border-color: var(--lamp-dim); }
.pin-card .pin-name {
  font: 12px var(--display); letter-spacing: .18em; text-transform: uppercase;
  color: var(--lamp); display: flex; align-items: baseline; gap: 8px;
}
.pin-card .pin-tack { color: var(--lamp-dim); font-size: 10px; }
.pin-card .chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 9px; }
.pin-card .chip {
  font: 10px var(--display); letter-spacing: .12em; text-transform: uppercase;
  border: 1px solid var(--drape-edge); color: var(--dim); padding: 2px 6px; border-radius: 2px;
}
.pin-card .chip.room { color: var(--lamp-dim); border-color: var(--lamp-dim); }
.pin-card .pin-prompt {
  font: 12px var(--typed); color: var(--dim); margin-top: 8px; line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.pin-card .pin-acts { display: flex; gap: 6px; margin-top: 11px; flex-wrap: wrap; }
.pin-card .act {
  background: none; border: 1px solid var(--drape-edge); color: var(--dim);
  font: 10px var(--display); letter-spacing: .14em; text-transform: uppercase;
  padding: 5px 10px; cursor: pointer; border-radius: 2px;
}
.pin-card .act:hover { border-color: var(--lamp-dim); color: var(--lamp); }
.pin-card .act.unpin:hover { border-color: var(--tattered); color: var(--tattered); }
</style>
