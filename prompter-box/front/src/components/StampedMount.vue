<script setup>
import {computed, reactive, ref} from 'vue';
import {canisterChips} from '../lib/canisters.js';

// The stamped mount ("The Print") — a fresh take framed like a developed
// print, any room, any kind. Acts are [{label, run}]; run receives
// {relabel, el} so an act can restamp its own button ("Cast — it is in the
// footage now") or read the mounted media, like the old handlers did.
const props = defineProps({
    room: {type: String, required: true},
    url: {type: String, required: true},
    kind: {type: String, required: true},
    title: {type: String, required: true},
    meta: {type: Object, default: () => ({})},
    stamp: {type: String, default: 'Fresh'},
    acts: {type: Array, default: () => []},
});

const fig = ref(null);
const chips = computed(() => canisterChips({room: props.room, meta: props.meta}, {fresh: true}));
const actRows = reactive(props.acts.map(a => ({...a})));
const runAct = act => act.run({
    relabel: label => {
        act.label = label;
    },
    el: fig.value,
});
</script>

<template>
  <figure ref="fig" class="mount" :data-room="room">
    <div class="mount-frame">
      <img v-if="kind === 'image'" :src="url" :alt="title">
      <audio v-else-if="kind === 'audio'" :src="url" controls></audio>
      <video v-else :src="url" controls loop></video>
      <span class="mount-stamp">{{ stamp }}</span>
    </div>
    <figcaption class="mount-body">
      <p class="mount-title">{{ title }}</p>
      <div class="mount-chips">
        <span v-for="([text, cls], i) in chips" :key="i" :class="cls">{{ text }}</span>
      </div>
      <div v-if="actRows.length" class="mount-acts">
        <button v-for="(act, i) in actRows" :key="i" class="act" @click="runAct(act)">{{ act.label }}</button>
      </div>
    </figcaption>
  </figure>
</template>

<style>
.mount {
  margin: 0; max-width: 760px; width: 100%;
  background: var(--paper);
  background-image: linear-gradient(175deg, var(--paper) 82%, var(--paper-shade));
  border-radius: 3px; box-shadow: 0 4px 20px rgba(0,0,0,.5); overflow: hidden;
}
.mount-frame { position: relative; background: #0d0b08; display: flex; justify-content: center; }
.mount-frame video, .mount-frame img { max-width: 100%; max-height: 62vh; display: block; }
.mount-frame audio { width: 100%; margin: 20px; }
.mount-stamp {
  position: absolute; top: 0; right: 0;
  font: 11px var(--display); letter-spacing: .26em; text-transform: uppercase; color: var(--ink);
  background: var(--lamp); padding: 5px 16px 5px 12px;
  clip-path: polygon(14px 0, 100% 0, 100% 100%, 0 100%);
}
.mount-body { padding: 14px 18px 16px; color: var(--ink); }
.mount-title { font: 13.5px var(--typed); line-height: 1.55; color: var(--ink); }
.mount-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; }
.mount .chip { border-color: #c9b98f; color: #6b5a3d; }
.mount .chip.room { color: #8a6a2e; border-color: #8a6a2e; }
.mount-acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.mount-acts .act {
  background: none; border: 1px solid #b9a985; color: #6b5a3d;
  font: 11px var(--display); letter-spacing: .16em; text-transform: uppercase;
  padding: 6px 12px; cursor: pointer; border-radius: 2px;
}
.mount-acts .act:hover { border-color: var(--ink); color: var(--ink); }
</style>
