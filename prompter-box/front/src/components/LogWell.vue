<script setup>
import {nextTick, ref, watch} from 'vue';

// The log well — the tail of a running job, pinned to the newest line.
// One definition for what the single-file front styled four times over
// (#stage-log, #kiln-log, #foley-log, #shift-log — identical declarations).
const props = defineProps({
    lines: {type: Array, default: () => []},
    shown: {type: Boolean, default: false},
});

const well = ref(null);
watch(() => props.lines, async () => {
    await nextTick();
    if (well.value) well.value.scrollTop = well.value.scrollHeight;
});
</script>

<template>
  <div v-show="shown" ref="well" class="log-well">{{ lines.join('\n') }}</div>
</template>

<style>
.log-well {
  background: var(--booth); border: 1px solid var(--drape-edge); border-radius: 2px;
  font: 12px var(--typed); color: var(--dim); padding: 12px 14px;
  max-height: 220px; overflow-y: auto; margin-top: 16px; white-space: pre-wrap;
}
</style>
