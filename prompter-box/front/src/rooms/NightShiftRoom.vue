<script setup>
import {Checkbox, NumberInput, TextInput} from '@script-development/ui-inputs';
import {onUnmounted, ref, watch} from 'vue';
import LogWell from '../components/LogWell.vue';
import {api} from '../composables/useBoothApi.js';

const props = defineProps({active: {type: Boolean, default: false}});

const subject = ref('');
const k = ref(1);
const twoSided = ref(false);
const rows = ref([]);
const running = ref(false);
const logLines = ref([]);
const logShown = ref(false);
const error = ref('');

function renderShift({rows: list, shift, log_tail}) {
    rows.value = list;
    running.value = Boolean(shift.running);
    if (log_tail?.length) {
        logShown.value = true;
        logLines.value = log_tail;
    }
}

async function loadShift() {
    error.value = '';
    try {
        renderShift(await api('/api/queue/list'));
    } catch (e) {
        error.value = e.message || String(e);
    }
}

// the call sheet refreshes every 3 s while the room is open
let timer = null;
watch(() => props.active, a => {
    clearInterval(timer);
    if (!a) return;
    loadShift();
    timer = setInterval(async () => {
        try {
            renderShift(await api('/api/queue/list'));
        } catch {
            // next tick retries
        }
    }, 3000);
}, {immediate: true});
onUnmounted(() => clearInterval(timer));

const progress = r => (r.status === 'queued' ? '—'
    : `take ${Math.min(r.takes_done + (r.status === 'firing' ? 1 : 0), r.variant_count)}/${r.variant_count}`);
const subjectText = r => (Array.isArray(r.subject) ? r.subject.join(' · ') : r.subject);

async function handle(fn) {
    error.value = '';
    try {
        await fn();
        loadShift();
    } catch (e) {
        error.value = e.message || String(e);
    }
}

const add = () => handle(async () => {
    const raw = subject.value.trim();
    if (!raw) throw new Error('An order needs a subject — the kiln fires nothing from an empty phrase.');
    // both grammars: semicolons list K distinct phrases; otherwise K seed-varied takes
    const phrases = raw.split(';').map(s => s.trim()).filter(Boolean);
    await api('/api/queue/add', {
        subject: phrases.length > 1 ? phrases : raw,
        variant_count: phrases.length > 1 ? phrases.length : (Number(k.value) || 1),
        job_type: 'kiln',
        two_sided: twoSided.value,
    });
    subject.value = '';
});
</script>

<template>
  <div class="panel">
    <div class="row">
      <div style="flex:3;min-width:220px">
        <label class="field" for="shift-subject">Add an order — a subject phrase</label>
        <TextInput id="shift-subject" v-model="subject" placeholder="terracotta geraniums in a weathered pot" />
      </div>
      <div style="max-width:90px">
        <label class="field" for="shift-k" title="K seed-varied takes of one subject, or list K phrases for K different props">K</label>
        <NumberInput
          id="shift-k" v-model="k" :min="1" :max="12"
          title="K seed-varied takes of one subject, or list K phrases for K different props"
        />
      </div>
      <div style="max-width:150px">
        <Checkbox id="shift-two-sided" v-model="twoSided" label="2-sided" />
      </div>
      <div style="max-width:110px"><button id="shift-add" class="fire" style="margin-top:0" @click="add">+ Add</button></div>
      <div style="max-width:220px">
        <button
          id="shift-start" class="fire" style="margin-top:0;white-space:nowrap" :disabled="running"
          @click="handle(() => api('/api/queue/start', {}))"
        >{{ running ? 'The shift is on the floor' : 'Start the shift' }}</button>
      </div>
      <div style="max-width:110px">
        <button
          id="shift-stop" class="act" style="margin-top:0;background:none;border:1px solid var(--drape-edge);color:var(--dim);font:11px var(--display);letter-spacing:.16em;text-transform:uppercase;padding:11px 16px;cursor:pointer;border-radius:2px"
          @click="handle(() => api('/api/queue/stop', {}))"
        >Stop</button>
      </div>
    </div>
    <p v-show="error" class="error">{{ error }}</p>
    <ul id="shift-rows">
      <li v-if="!rows.length" class="empty">The shift is dark — no orders on the call sheet. Brief a few and let them fire overnight.</li>
      <li v-for="r in rows" :key="r.id" class="order" :data-status="r.status">
        <i class="eye"></i>
        <span class="status">{{ r.status }}</span>
        <span class="subject" :title="subjectText(r)">{{ subjectText(r) }}</span>
        <span class="k">×{{ r.variant_count }}</span>
        <span class="progress">{{ progress(r) }}</span>
        <span v-if="r.status === 'failed' && r.reason" class="reason" :title="r.reason">{{ r.reason }}</span>
        <span class="handles">
          <button class="act" @click="handle(() => api('/api/queue/reorder', {row_id: r.id, direction: 'up'}))">↑</button>
          <button class="act" @click="handle(() => api('/api/queue/reorder', {row_id: r.id, direction: 'down'}))">↓</button>
          <button class="act" @click="handle(() => api('/api/queue/remove', {row_id: r.id}))">remove</button>
        </span>
      </li>
    </ul>
    <LogWell :lines="logLines" :shown="logShown" />
  </div>
</template>

<style>
#shift-rows { list-style: none; padding: 0; margin: 16px 0 0; display: grid; gap: 8px; }
.order {
  display: flex; align-items: center; gap: 10px;
  background: var(--booth); border: 1px solid var(--drape-edge); border-radius: 3px;
  padding: 9px 12px;
}
.order .eye {
  flex: none; width: 11px; height: 11px; border-radius: 50%;
  background: var(--stage-off); box-shadow: inset 0 1px 2px rgba(0,0,0,.7);
}
.order[data-status="queued"] .eye { background: var(--lamp-dim); opacity: .5; }
.order[data-status="firing"] .eye {
  background: radial-gradient(circle at 40% 35%, var(--filament), var(--lamp) 70%);
  box-shadow: 0 0 8px rgba(232,176,74,.9); animation: eye-pulse 1.4s ease-in-out infinite;
}
.order[data-status="done"] .eye { background: var(--cured); box-shadow: 0 0 6px rgba(125,161,107,.5); }
.order[data-status="failed"] .eye { background: var(--tattered); box-shadow: 0 0 6px rgba(194,84,58,.6); }
.order .status { font: 10px var(--display); letter-spacing: .18em; text-transform: uppercase;
                 color: var(--dim); width: 52px; flex: none; }
.order[data-status="firing"] .status { color: var(--filament); }
.order[data-status="done"] .status { color: var(--cured); }
.order[data-status="failed"] .status { color: var(--tattered); }
.order .subject { font: 12.5px var(--typed); color: var(--paper); flex: 1;
                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.order .k, .order .progress { font: 11px var(--typed); color: var(--dim); flex: none; }
.order .reason { font-size: 11px; font-style: italic; color: var(--tattered); flex: 2;
                 overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.order .handles { display: flex; gap: 4px; flex: none; }
.order .handles .act {
  background: none; border: 1px solid var(--drape-edge); color: var(--dim);
  font: 10px var(--display); letter-spacing: .1em; text-transform: uppercase;
  padding: 3px 8px; cursor: pointer; border-radius: 2px;
}
.order .handles .act:hover { border-color: var(--lamp-dim); color: var(--lamp); }
</style>
