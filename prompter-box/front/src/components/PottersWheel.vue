<script setup lang="ts">
import {onMounted, onUnmounted, ref} from 'vue';
import type {WheelMount} from '../lib/potters-wheel';

// The Potter's Wheel, wrapped — the module is fresh and tested-in-anger, so
// the wrapper only owns the Vue lifecycle: mount on the well, hold the
// poster until the piece is ready, dispose on unmount (#00063 §4A). If the
// wheel jams, the poster stands.
const props = withDefaults(defineProps<{
    glbUrl: string;
    initialYaw?: number;
    posterSrc?: string;
    posterClass?: string;
    posterAlt?: string;
    hint?: string;
}>(), {
    initialYaw: 0,
    posterSrc: '',
    posterClass: '',
    posterAlt: '',
    hint: 'take it by the rim — drag to see every side, scroll to lean in',
});

const well = ref<HTMLElement | null>(null);
const ready = ref(false);
const spun = ref(false);
let handle: WheelMount | null = null;

onMounted(async () => {
    try {
        // lazy, like the old front's `import('/static/potters-wheel.js')` —
        // three.js stays out of the shell bundle until a piece needs turning
        const {mountWheel} = await import('../lib/potters-wheel');
        handle = mountWheel(well.value!, props.glbUrl, {
            initialYaw: props.initialYaw,
            reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
        });
        await handle.ready;
        ready.value = true;
    } catch {
        // no wheel? the still frame stands
    }
});
onUnmounted(() => {
    handle?.dispose();
    handle = null;
});
</script>

<template>
  <div ref="well" class="wheel" :class="{spun}" @pointerdown.once="spun = true">
    <img v-if="!ready && posterSrc" :src="posterSrc" :class="posterClass" :alt="posterAlt">
    <p v-if="ready" class="wheel-hint">{{ hint }}</p>
    <slot />
  </div>
</template>

<style>
/* the Potter's Wheel — grab the piece and turn it */
.wheel { position: relative; cursor: grab; touch-action: none; }
.wheel:active { cursor: grabbing; }
.wheel canvas.wheel-canvas {
  position: absolute; inset: 0; display: block;
  width: 100% !important; height: 100% !important;
}
.mount-frame .wheel { width: min(100%, 420px); height: 320px; }
.wheel-hint {
  position: absolute; left: 8px; bottom: 6px; margin: 0; pointer-events: none; z-index: 2;
  font-size: 10.5px; font-style: italic; color: var(--dim); opacity: .85;
}
.wheel.spun .wheel-hint { opacity: 0; transition: opacity .6s ease; }
</style>
