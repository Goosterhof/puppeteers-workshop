<script setup lang="ts">
import {ref, watch} from 'vue';

// The full ComfyUI house — same lazy first-entry activation as the Stage UI.
const props = withDefaults(defineProps<{active?: boolean}>(), {active: false});
const src = ref<string | undefined>(undefined);
watch(() => props.active, a => {
    if (a && !src.value) src.value = 'http://localhost:8188';
}, {immediate: true});
</script>

<template>
  <div class="house">
    <p class="note">The full ComfyUI house on <a href="http://localhost:8188" target="_blank">:8188</a> — raise it with <code>./start-comfyui.sh</code>.</p>
    <iframe :src="src" title="ComfyUI"></iframe>
  </div>
</template>
