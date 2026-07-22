<script setup lang="ts">
import {NumberInput, SingleSelect, Textarea} from '@script-development/ui-inputs';
import {computed, onMounted, ref} from 'vue';
import ThumbRow from '../components/ThumbRow.vue';
import {api} from '../composables/useBoothApi';
import {facePrompt, forgeLead, leadRes, openTab, pickedImage, stagePrompt} from '../stores/booth';

const TARGETS = [
    {t: 'wan', label: 'Stage · motion', stamp: 'stage · motion'},
    {t: 'flux', label: 'Face · image', stamp: 'face · image'},
    {t: 'relay', label: 'Relay · timed', stamp: 'relay · timed'},
];

interface CueCard {
    n: number;
    text: string;
    target: string;
    lead: string | null;
}

const idea = ref('');
const target = ref('wan');
const variants = ref(3);
const voice = ref('');
const voices = ref<{name: string; label: string}[]>([]);
const busy = ref(false);
const error = ref('');
const cards = ref<CueCard[]>([]);
const room = ref<HTMLElement | null>(null);

async function strike() {
    error.value = '';
    if (!idea.value.trim()) {
        error.value = 'The forge needs raw material — give it an idea.';
        return;
    }
    busy.value = true;
    try {
        const lead = forgeLead.value;
        const t = target.value;
        const {variants: texts} = await api<{variants: string[]}>('/api/forge', {
            target: t, idea: idea.value.trim(), variants: Number(variants.value),
            image: lead, model: voice.value || undefined,
        });
        cards.value = texts.map((text, i) => ({n: i + 1, text, target: t, lead}));
    } catch (e) {
        error.value = (e as Error).message || String(e);
    }
    busy.value = false;
}

const stampFor = (card: CueCard) => {
    const base = TARGETS.find(x => x.t === card.target)!.stamp;
    return card.lead ? `${base} · sighted` : base;
};
const copyCue = (text: string) => navigator.clipboard.writeText(text);

function cueStage(card: CueCard) {
    stagePrompt.value = card.text;
    if (card.lead) {
        pickedImage.value = card.lead;
        const t = room.value?.querySelector<HTMLImageElement>(`.thumbrow img[title="${CSS.escape(card.lead)}"]`);
        if (t?.naturalWidth) leadRes.value = {w: t.naturalWidth, h: t.naturalHeight};
    }
    openTab('stage');
}
function cueFace(card: CueCard) {
    facePrompt.value = card.text;
    openTab('face');
}
const pickLead = (name: string) => {
    forgeLead.value = forgeLead.value === name ? null : name;
};

async function loadVoices() {
    try {
        const {models, default_text, default_vision} = await api<{models: string[]; default_text?: string; default_vision?: string}>('/api/forge/models');
        voices.value = models.map(name => ({
            name,
            label: name + (name === default_text ? ' · house text voice'
                : name === default_vision ? ' · house vision voice' : ''),
        }));
    } catch {
        // forge cold — the booth decides, as ever
    }
}

// booth-decides rides as a real option (id '') — picking a voice must stay
// reversible, exactly like the old empty <option>
const voiceOptions = computed(() => [
    {id: '', label: '— the booth decides —'},
    ...voices.value.map(v => ({id: v.name, label: v.label})),
]);
onMounted(loadVoices);
</script>

<template>
  <div ref="room">
    <div class="panel">
      <label class="field" for="idea">The rough idea</label>
      <Textarea id="idea" v-model="idea" placeholder="illustrated town crier mascot — the bell in his chest alcove swings and rings; scroll stays still…" />
      <label class="field">The lead — optional; gives the Promptsmith eyes (click to pick, click again to clear)</label>
      <ThumbRow id="forge-thumbs" :picked="forgeLead" @pick="pickLead" />
      <div class="row" style="margin-top:14px">
        <div>
          <label class="field">Cue type</label>
          <div id="targets" class="pills">
            <button
              v-for="x in TARGETS" :key="x.t"
              :aria-pressed="target === x.t" :data-t="x.t"
              @click="target = x.t"
            >{{ x.label }}</button>
          </div>
        </div>
        <div style="max-width:110px">
          <label class="field" for="variants">Variants</label>
          <NumberInput id="variants" v-model="variants" :min="1" :max="6" />
        </div>
        <div style="max-width:230px">
          <label class="field" for="forge-model">The voice</label>
          <SingleSelect
            id="forge-model" v-model="voice"
            :options="voiceOptions" label="label" :alphabetical-sort="false"
            options-label="The voices on the Ollama shelf"
          />
        </div>
        <div style="max-width:210px">
          <button id="strike" class="fire" style="margin-top:0" :disabled="busy" @click="strike">{{ busy ? 'Forging…' : 'Strike the forge' }}</button>
        </div>
      </div>
      <p id="forge-note" class="note">First strike after idle loads the model — allow ~15 s. After that it's a few seconds.</p>
      <p v-show="error" class="error">{{ error }}</p>
    </div>
    <div id="cards">
      <p v-if="!cards.length" class="empty">The rack is empty — strike the forge and the cue cards deal here.</p>
      <article v-for="card in cards" :key="`${card.n}-${card.text}`" class="card">
        <div class="stamp"><span>Cue № {{ card.n }}</span><span>{{ stampFor(card) }}</span></div>
        <p>{{ card.text }}</p>
        <div class="acts">
          <button @click="copyCue(card.text)">Copy</button>
          <button v-if="card.target !== 'flux'" @click="cueStage(card)">Cue the stage →</button>
          <button v-if="card.target !== 'relay'" @click="cueFace(card)">Cue the face shop →</button>
        </div>
      </article>
    </div>
  </div>
</template>

<style>
#cards { display: grid; gap: 18px; margin-top: 26px; }
.card {
  background: var(--paper);
  background-image: linear-gradient(175deg, var(--paper) 82%, var(--paper-shade));
  color: var(--ink);
  border-radius: 2px;
  padding: 18px 20px 14px;
  clip-path: polygon(0 0, calc(100% - 18px) 0, 100% 18px, 100% 100%, 0 100%);
  box-shadow: 0 3px 14px rgba(0,0,0,.45);
  animation: deal .35s ease-out backwards;
}
.card:nth-child(2) { animation-delay: .08s; }
.card:nth-child(3) { animation-delay: .16s; }
.card:nth-child(4) { animation-delay: .24s; }
@keyframes deal { from { opacity: 0; transform: translateY(14px); } }
.card .stamp {
  font-family: var(--display); font-size: 11px; letter-spacing: .26em; text-transform: uppercase;
  color: #8a7350; border-bottom: 1px solid #d5c7a8; padding-bottom: 6px; margin-bottom: 10px;
  display: flex; justify-content: space-between;
}
.card p { font-family: var(--typed); font-size: 13.5px; line-height: 1.65; }
.card .acts { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.card .acts button {
  background: none; border: 1px solid #b9a985; color: #6b5a3d;
  font: 11px var(--display); letter-spacing: .16em; text-transform: uppercase;
  padding: 6px 12px; cursor: pointer; border-radius: 2px;
}
.card .acts button:hover { border-color: var(--ink); color: var(--ink); }
#forge-thumbs img { height: 62px; }
</style>
