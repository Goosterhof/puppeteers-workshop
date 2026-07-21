<script setup>
import {ref} from 'vue';

// The breaking pit — the Rack's confirm before a firing becomes shards.
// Three exits: Keep it curing, Esc (both keep the candidate), Break it.
const emit = defineEmits(['break']);
const dialog = ref(null);
const subject = ref('');
let target = null;

function open(entry) {
    target = entry;
    subject.value = `“${entry.recipe.canister_label || entry.recipe.subject}” — ${entry.id}`;
    dialog.value.showModal();
}
function keep() {
    target = null;
    dialog.value.close();
}
function onCancel() {
    target = null; // Esc keeps it curing
}
function breakIt() {
    const entry = target;
    target = null;
    dialog.value.close();
    if (entry) emit('break', entry);
}
defineExpose({open});
</script>

<template>
  <dialog id="break-pit" ref="dialog" @cancel="onCancel">
    <h2>Break this firing?</h2>
    <p class="break-subject">{{ subject }}</p>
    <p>The painting, the mesh, the QA report, the turntable frames — shards.
      Nothing comes back from the reject pile.</p>
    <div class="acts">
      <button id="break-keep" class="act" @click="keep">Keep it curing</button>
      <button id="break-confirm" class="fire danger" @click="breakIt">Break it</button>
    </div>
  </dialog>
</template>

<style>
dialog#break-pit {
  background: var(--drape); border: 1px solid var(--drape-edge);
  border-radius: 3px; padding: 24px 28px; max-width: 460px; margin: auto;
}
dialog#break-pit::backdrop { background: rgba(0, 0, 0, .65); }
dialog#break-pit h2 {
  font: 15px var(--display); letter-spacing: .14em; text-transform: uppercase;
  color: var(--tattered);
}
dialog#break-pit p { font-size: 12.5px; color: var(--dim); line-height: 1.55; margin-top: 10px; }
dialog#break-pit .break-subject { color: var(--filament); font-style: italic; }
dialog#break-pit .acts { display: flex; gap: 10px; margin-top: 18px; justify-content: flex-end; }
dialog#break-pit .fire { margin-top: 0; }
dialog#break-pit .act {
  background: none; border: 1px solid var(--drape-edge); color: var(--dim);
  font: 11px var(--display); letter-spacing: .16em; text-transform: uppercase;
  padding: 11px 16px; cursor: pointer; border-radius: 2px;
}
dialog#break-pit .act:hover { border-color: var(--lamp); color: var(--lamp); }
</style>
