<script setup lang="ts">
import {computed, ref} from 'vue';
import {ROOM_JOURNEYS} from '../lib/room-flows';

const props = withDefaults(defineProps<{room: string; current?: number}>(), {current: 0});
const journey = computed(() => ROOM_JOURNEYS[props.room]!);
const root = ref<HTMLElement | null>(null);
function visit(target: string) {
    const panel = root.value?.closest('[role="tabpanel"]') ?? root.value?.parentElement;
    const el = panel?.querySelector<HTMLElement>(target);
    if (!el) return;
    for (let p: HTMLElement | null = el; p; p = p.parentElement) {
        if (p instanceof HTMLDetailsElement) p.open = true;
    }
    el.scrollIntoView({block: 'nearest', behavior: 'auto'});
    const focus = el.matches('input, textarea, button, a, iframe') ? el
        : el.querySelector<HTMLElement>('input:not([type="hidden"]), textarea, button, a');
    focus?.focus({preventScroll: true});
}
</script>

<template>
  <header ref="root" class="room-flow">
    <h2>{{ journey.title }}</h2>
    <p>{{ journey.purpose }}</p>
    <nav :aria-label="`${journey.title} — working steps`">
      <ol>
        <li v-for="(step, i) in journey.steps" :key="step.label">
          <button :aria-current="current === i ? 'step' : undefined" @click="visit(step.target)">
            <span class="step-number">{{ i + 1 }}</span>{{ step.label }}
          </button>
        </li>
      </ol>
    </nav>
  </header>
</template>

<style>
.room-flow { margin: 0 0 22px; color: var(--ink); }
.room-flow h2 { font: 500 25px var(--display); margin: 0 0 7px; }
.room-flow p { font: 12.5px/1.6 var(--typed); color: var(--ink-soft); margin: 0 0 15px; max-width: 76ch; }
.room-flow ol { list-style: none; display: flex; flex-wrap: wrap; gap: 8px; padding: 0; margin: 0; }
.room-flow button { display: flex; gap: 7px; align-items: center; padding: 7px 10px; border: 1px solid var(--ink-hair); background: transparent; color: var(--ink-soft); cursor: pointer; font: 11px var(--typed); border-radius: 2px; }
.room-flow button[aria-current="step"] { border-color: var(--ink); color: var(--ink); background: var(--page-shade); font-weight: 700; }
.room-flow button:focus-visible { outline: 2px solid var(--ink); outline-offset: 3px; }
.step-number { font-size: 10px; opacity: .65; }
.flow-heading { font: 500 16px var(--display); color: var(--ink); margin: 24px 0 12px; }
.task-picks { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 18px; }
.task-picks button { background: var(--page); border: 1px solid var(--ink-hair); color: var(--ink-soft); padding: 10px 14px; cursor: pointer; font: 12px var(--typed); border-radius: 2px; }
.task-picks button[aria-pressed="true"] { border-color: var(--ink); color: var(--ink); box-shadow: inset 0 -2px var(--ink); }
.task-picks button:focus-visible { outline: 2px solid var(--ink); outline-offset: 3px; }
.room-settings { margin-top: 18px; padding: 12px 0; border-top: 1px solid var(--ink-hair); }
.room-settings summary { cursor: pointer; color: var(--ink-soft); font: 12px var(--typed); }
.room-settings > label:first-of-type { margin-top: 16px; }
</style>
