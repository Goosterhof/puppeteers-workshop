<script setup lang="ts">
import {ref} from 'vue';

// The bin — the confirm before a take leaves the booth for good (2026-08-23).
// The Rack has its BreakPit for firings; this is the print's own, for a
// painting, a take, a score, or a shelved still. Three exits: Keep it, Esc
// (both keep), Bin it.
const emit = defineEmits<{bin: [filename: string]}>();
const dialog = ref<HTMLDialogElement | null>(null);
const subject = ref('');
let target: string | null = null;

function open(filename: string) {
    target = filename;
    subject.value = filename;
    dialog.value?.showModal();
}
function keep() {
    target = null;
    dialog.value?.close();
}
function onCancel() {
    target = null;
}
function binIt() {
    const name = target;
    target = null;
    dialog.value?.close();
    if (name) emit('bin', name);
}
defineExpose({open});
</script>

<template>
  <dialog ref="dialog" class="take-bin" @cancel="onCancel">
    <h2>Bin this take?</h2>
    <p class="bin-subject">{{ subject }}</p>
    <p>It comes off the rack and off the bench's disk. Nothing comes back from the bin —
      if you might want it again, Download it first.</p>
    <div class="acts">
      <button type="button" class="act bin-keep" @click="keep">Keep it</button>
      <button type="button" class="fire danger bin-confirm" @click="binIt">Bin it</button>
    </div>
  </dialog>
</template>

<style>
dialog.take-bin {
  background: var(--drape); border: 1px solid var(--drape-edge);
  border-radius: 3px; padding: 24px 28px; max-width: 460px; margin: auto;
}
dialog.take-bin::backdrop { background: rgba(0, 0, 0, .65); }
dialog.take-bin h2 {
  font: 15px var(--display); letter-spacing: .14em; text-transform: uppercase;
  color: var(--tattered);
}
dialog.take-bin p { font-size: 12.5px; color: var(--dim); line-height: 1.55; margin-top: 10px; }
dialog.take-bin .bin-subject { color: var(--filament); font-style: italic; font-family: var(--typed); word-break: break-all; }
dialog.take-bin .acts { display: flex; gap: 10px; margin-top: 18px; justify-content: flex-end; }
dialog.take-bin .fire { margin-top: 0; }
dialog.take-bin .act {
  background: none; border: 1px solid var(--drape-edge); color: var(--dim);
  font: 11px var(--display); letter-spacing: .16em; text-transform: uppercase;
  padding: 11px 16px; cursor: pointer; border-radius: 2px;
}
dialog.take-bin .act:hover { border-color: var(--lamp); color: var(--lamp); }
/* on the lit page the hot filament has nothing dark to glow against */
.folio-page dialog.take-bin .bin-subject { color: var(--ember); }
.folio-page dialog.take-bin .act:hover { border-color: var(--ember); color: var(--ember); }
</style>
