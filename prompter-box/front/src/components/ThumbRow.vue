<script setup lang="ts">
import {ref} from 'vue';
import {STILL_ACCEPT, looksLikeStill} from '../lib/still';
import {footage, shelveStill} from '../stores/booth';

// One footage shelf, three rooms — the Forge's lead, the Stage's start
// image, the Face Shop's sitter each pick from the same strip. Since
// 2026-08-23 the strip has a hatch at its head: bring your own still (file
// picker or drag-and-drop) and it lands on the shelf for all three rooms,
// picked on arrival so upload → cue → paint is one motion.
withDefaults(defineProps<{picked?: string | null}>(), {picked: null});
const emit = defineEmits<{pick: [name: string]}>();

const hatch = ref<HTMLInputElement | null>(null);
const hovering = ref(false);
const shelving = ref<string | null>(null);
const refusal = ref<string | null>(null);

async function bring(files: FileList | File[] | null | undefined) {
    const stills = Array.from(files ?? []).filter(looksLikeStill);
    refusal.value = null;
    if (!stills.length) {
        if (files?.length) refusal.value = 'The shelf takes stills only — PNG, JPEG, or WebP.';
        return;
    }
    let last: string | null = null;
    for (const file of stills) {
        shelving.value = file.name;
        try {
            last = await shelveStill(file);
        } catch (e) {
            refusal.value = e instanceof Error ? e.message : String(e);
            break;
        }
    }
    shelving.value = null;
    if (last) emit('pick', last);
}

function onPick(e: Event) {
    const input = e.target as HTMLInputElement;
    void bring(input.files).finally(() => {
        input.value = ''; // the same file twice must fire twice
    });
}
function onDrop(e: DragEvent) {
    hovering.value = false;
    void bring(e.dataTransfer?.files);
}
</script>

<template>
  <div
    class="thumbrow thumbrow--shelf" :class="{hovering}"
    @dragover.prevent="hovering = true" @dragleave="hovering = false" @drop.prevent="onDrop"
  >
    <button
      type="button" class="hatch" :class="{shelving: !!shelving}" :disabled="!!shelving"
      :title="shelving ? `Shelving ${shelving}…` : 'Bring your own still — pick a PNG, JPEG, or WebP, or drop one anywhere on the shelf'"
      @click="hatch?.click()"
    >
      <span class="hatch-mark">{{ shelving ? '…' : '+' }}</span>
      <span class="hatch-word">{{ shelving ? 'shelving' : 'bring a still' }}</span>
    </button>
    <input ref="hatch" type="file" :accept="STILL_ACCEPT" multiple hidden @change="onPick">
    <p v-if="!footage.length" class="empty">No footage on the shelf — bring a still through the hatch, drop one here, or drop files into <code>footage/</code>.</p>
    <img
      v-for="name in footage" :key="name"
      :src="`/footage/${encodeURIComponent(name)}`" :title="name" :alt="name"
      :class="{picked: picked === name}"
      @click="emit('pick', name)"
    >
    <p v-if="refusal" class="refusal" role="alert">{{ refusal }}</p>
  </div>
</template>

<style>
/* The hatch: the one tile on the strip that is a door, not a still. It wears
   the strip's 86px height so it reads as a member of the row, and a dashed
   border so it never passes for footage. */
.thumbrow--shelf { position: relative; align-items: center; }
.thumbrow--shelf .hatch {
  height: 86px; min-width: 86px; padding: 0 12px; box-sizing: border-box;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;
  border: 2px dashed var(--dim); border-radius: 2px; background: transparent; color: var(--dim);
  cursor: pointer; opacity: .75; transition: opacity .15s, border-color .15s, color .15s;
}
.thumbrow--shelf .hatch:hover, .thumbrow--shelf .hatch:focus-visible,
.thumbrow--shelf.hovering .hatch { opacity: 1; border-color: var(--lamp); color: var(--lamp); }
.thumbrow--shelf.hovering { outline: 2px dashed var(--lamp); outline-offset: 4px; }
.thumbrow--shelf .hatch.shelving { cursor: progress; border-style: solid; }
.thumbrow--shelf .hatch-mark { font: 26px/1 var(--display); }
.thumbrow--shelf .hatch-word { font: 10px var(--display); letter-spacing: .16em; text-transform: uppercase; }
.thumbrow--shelf .refusal { flex-basis: 100%; margin: 2px 0 0; font-size: 12px; color: var(--ember); }
.folio-page .thumbrow--shelf .hatch:hover, .folio-page .thumbrow--shelf .hatch:focus-visible,
.folio-page .thumbrow--shelf.hovering .hatch { border-color: var(--ember); color: var(--ember); }
.folio-page .thumbrow--shelf.hovering { outline-color: var(--ember); }
</style>
