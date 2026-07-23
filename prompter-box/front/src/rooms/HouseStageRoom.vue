<script setup lang="ts">
import {ref, watch} from 'vue';

// The full Wan2GP house — the iframe stays cold until the tab is first
// entered (the old data-src activation), then keeps its state across tabs.
const props = withDefaults(defineProps<{active?: boolean}>(), {active: false});
const src = ref<string | undefined>(undefined);
watch(() => props.active, a => {
    if (a && !src.value) src.value = 'http://localhost:7860';
}, {immediate: true});
</script>

<template>
  <div class="house">
    <p class="note">The full Wan2GP house on <a href="http://localhost:7860" target="_blank">:7860</a> — raise it with <code>./start-wangp.sh</code>. Note: while the full UI holds the stage, the booth's own Stage cues are refused (one GPU, one performance).</p>
    <iframe :src="src" title="Wan2GP"></iframe>
  </div>
</template>

<style>
.house iframe { width: 100%; height: 78vh; border: 1px solid var(--drape-edge); border-radius: 3px; background: #111; }
.house .note a { color: var(--lamp); }
</style>
