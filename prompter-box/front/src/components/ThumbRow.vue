<script setup lang="ts">
import {footage} from '../stores/booth';

// One footage shelf, three rooms — the Forge's lead, the Stage's start
// image, the Face Shop's sitter each pick from the same strip.
withDefaults(defineProps<{picked?: string | null}>(), {picked: null});
const emit = defineEmits<{pick: [name: string]}>();
</script>

<template>
  <div class="thumbrow">
    <p v-if="!footage.length" class="empty">No footage on the shelf — drop stills into <code>footage/</code> and they appear here.</p>
    <img
      v-for="name in footage" :key="name"
      :src="`/footage/${encodeURIComponent(name)}`" :title="name" :alt="name"
      :class="{picked: picked === name}"
      @click="emit('pick', name)"
    >
  </div>
</template>
