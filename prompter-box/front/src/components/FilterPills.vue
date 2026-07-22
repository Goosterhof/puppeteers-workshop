<script setup lang="ts">
withDefaults(defineProps<{
    options: {value: string; label: string}[];
    modelValue?: string;
}>(), {
    modelValue: '',
});
const emit = defineEmits<{'update:modelValue': [value: string]}>();
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
