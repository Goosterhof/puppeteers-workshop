<script lang="ts">
// The context an act's run() receives — restamp the button, read the mount.
export interface MountActContext {
    relabel: (label: string) => void;
    el: HTMLElement | null;
}

// One act row under the print — exported so the rooms can type their acts.
export interface MountAct {
    label: string;
    run: (ctx: MountActContext) => unknown;
}
</script>

<script setup lang="ts">
import {computed, reactive, ref} from 'vue';
import type {CanisterMeta, RoomName, ShelfItem} from '../lib/canisters';
import {canisterChips} from '../lib/canisters';
import {clipboardTakesImages, copyImageToClipboard, downloadName} from '../lib/take-home';

// The stamped mount ("The Print") — a fresh take framed like a developed
// print, any room, any kind. Acts are [{label, run}]; run receives
// {relabel, el} so an act can restamp its own button ("Cast — it is in the
// footage now") or read the mounted media, like the old handlers did.
const props = withDefaults(defineProps<{
    room: RoomName;
    url: string;
    kind: string;
    title: string;
    meta?: CanisterMeta;
    stamp?: string;
    acts?: MountAct[];
}>(), {
    meta: () => ({}),
    stamp: 'Fresh',
    acts: () => [],
});

const fig = ref<HTMLElement | null>(null);
const chips = computed(() => canisterChips({room: props.room, meta: props.meta} as ShelfItem, {fresh: true}));
const actRows = reactive(props.acts.map(a => ({...a})));
const runAct = (act: MountAct) => act.run({
    relabel: label => {
        act.label = label;
    },
    el: fig.value,
});

// Take it home (2026-08-23): every mount carries its own way out of the
// booth — a download that lands in the browser's Downloads, and for images a
// clipboard copy. The take already lives on the bench's disk, but a WSL path
// is not a place the investor wants to go digging.
const filename = computed(() => downloadName(props.url));
const canCopy = computed(() => props.kind === 'image' && clipboardTakesImages());
const copyLabel = ref('Copy image');
let copyTimer: ReturnType<typeof setTimeout> | undefined;
async function copyTake() {
    clearTimeout(copyTimer);
    try {
        await copyImageToClipboard(props.url);
        copyLabel.value = 'Copied — paste it anywhere';
    } catch (e) {
        copyLabel.value = e instanceof Error ? e.message : 'Copy failed';
    }
    copyTimer = setTimeout(() => {
        copyLabel.value = 'Copy image';
    }, 2500);
}
</script>

<template>
  <figure ref="fig" class="mount" :data-room="room">
    <div class="mount-frame">
      <img v-if="kind === 'image'" :src="url" :alt="title">
      <audio v-else-if="kind === 'audio'" :src="url" controls></audio>
      <video v-else :src="url" controls loop></video>
      <span class="mount-stamp">{{ stamp }}</span>
    </div>
    <figcaption class="mount-body">
      <p class="mount-title">{{ title }}</p>
      <div class="mount-chips">
        <span v-for="([text, cls], i) in chips" :key="i" :class="cls">{{ text }}</span>
      </div>
      <div class="mount-acts">
        <a class="act take-home" :href="url" :download="filename" :title="`Save ${filename} to your downloads`">Download ↓</a>
        <button v-if="canCopy" class="act take-home" :title="`Copy ${filename} to the clipboard as PNG`" @click="copyTake">{{ copyLabel }}</button>
        <button v-for="(act, i) in actRows" :key="i" class="act" @click="runAct(act)">{{ act.label }}</button>
      </div>
    </figcaption>
  </figure>
</template>

<style>
.mount {
  margin: 0; max-width: 760px; width: 100%;
  background: var(--paper);
  background-image: linear-gradient(175deg, var(--paper) 82%, var(--paper-shade));
  border-radius: 3px; box-shadow: 0 4px 20px rgba(0,0,0,.5); overflow: hidden;
}
/* A developed print is paper in both lights. The folio remaps --paper to ink
   (bright text becomes ink on the page), which turned the print's body dark
   under its own ink-coloured title and act labels — so on the folio the
   print reads the --page primitives, which never chase the remap. */
.folio-page .mount {
  background: var(--page);
  background-image: linear-gradient(175deg, var(--page) 82%, var(--page-shade));
}
.mount-frame { position: relative; background: #0d0b08; display: flex; justify-content: center; }
.mount-frame video, .mount-frame img { max-width: 100%; max-height: 62vh; display: block; }
.mount-frame audio { width: 100%; margin: 20px; }
.mount-stamp {
  position: absolute; top: 0; right: 0;
  font: 11px var(--display); letter-spacing: .26em; text-transform: uppercase; color: var(--ink);
  background: var(--lamp); padding: 5px 16px 5px 12px;
  clip-path: polygon(14px 0, 100% 0, 100% 100%, 0 100%);
}
.mount-body { padding: 14px 18px 16px; color: var(--ink); }
.mount-title { font: 13.5px var(--typed); line-height: 1.55; color: var(--ink); }
.mount-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; }
.mount .chip { border-color: #c9b98f; color: #6b5a3d; }
.mount .chip.room { color: #8a6a2e; border-color: #8a6a2e; }
.mount-acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.mount-acts .act {
  background: none; border: 1px solid #b9a985; color: #6b5a3d;
  font: 11px var(--display); letter-spacing: .16em; text-transform: uppercase;
  padding: 6px 12px; cursor: pointer; border-radius: 2px;
}
.mount-acts .act:hover { border-color: var(--ink); color: var(--ink); }
.mount-acts a.act { text-decoration: none; display: inline-block; line-height: normal; }
.mount-acts .act.take-home { border-style: dashed; }
</style>
