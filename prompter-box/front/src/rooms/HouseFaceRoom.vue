<script setup lang="ts">
import {ref, watch} from 'vue';
import RoomFlow from '../components/RoomFlow.vue';
import {openTab} from '../stores/booth';

// The full ComfyUI house — same lazy first-entry activation as the Stage UI.
const props = withDefaults(defineProps<{active?: boolean}>(), {active: false});
const src = ref<string | undefined>(undefined);
watch(() => props.active, a => {
    if (a && !src.value) src.value = 'http://localhost:8188';
}, {immediate: true});
</script>

<template>
  <RoomFlow room="house-face" :current="src ? 1 : 0" />
  <div class="house">
    <p class="note">The full ComfyUI house on <a id="house-face-open" href="http://localhost:8188" target="_blank">:8188</a> — raise it with <code>./start-comfyui.sh</code>.</p>
    <div class="task-picks"><button id="house-face-collect" @click="openTab('archive')">Collect finished paintings in The Canisters →</button></div>
    <iframe id="house-face-frame" :src="src" title="ComfyUI"></iframe>
  </div>
</template>
