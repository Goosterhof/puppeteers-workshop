<script setup>
defineProps({
    options: {type: Array, required: true},
    modelValue: {type: String, default: ''},
});
const emit = defineEmits(['update:modelValue']);
</script>

<template>
  <div class="pills">
    <button
      v-for="o in options" :key="o.value"
      :aria-pressed="modelValue === o.value"
      @click="emit('update:modelValue', o.value)"
    >{{ o.label }}</button>
  </div>
</template>
