import {ref} from 'vue';
import {api} from '../composables/useBoothApi';
import {readStill} from '../lib/still';

// The booth's shared state — the module-global era's cross-room wires
// (forgeLead, pickedImage, faceSitter, the footage shelf, tab navigation)
// gathered into one reactive store (#00063 Phase 2). Plain module-scoped
// refs, no store library: eleven rooms, one booth.

export const activeTab = ref('forge');
export const openTab = (name: string) => {
    activeTab.value = name;
};

// The leads: what the Promptsmith looks at, what the Stage starts from,
// what the Face Shop edits.
export const forgeLead = ref<string | null>(null);
export const pickedImage = ref<string | null>(null);
export const faceSitter = ref<string | null>(null);

// The cues in flight — "Cue the stage →" and "Cue the face shop →" write
// into another room's prompt box, so the boxes live here.
export const stagePrompt = ref('');
export const facePrompt = ref('');

// A cast lead's natural size, parked for the Stage's resolution matcher —
// consumed when the Stage room rises in Phase 3.
export const leadRes = ref<{w: number; h: number} | null>(null);

export const footage = ref<string[]>([]);
export async function loadFootage(preselect?: string) {
    footage.value = (await api<{images: string[]}>('/api/footage')).images;
    if (preselect) pickedImage.value = preselect;
}

// The Foley Booth's reel shelf — shared so other rooms can preselect a take
// ("Score it in the foley booth →") before opening the tab.
export const foleySources = ref<{footage: string[]; stage: string[]}>({footage: [], stage: []});
export const foleyReel = ref('');
export async function loadFoleySources(preselect?: string) {
    foleySources.value = await api<{footage: string[]; stage: string[]}>('/api/foley/sources');
    const keep = preselect ?? foleyReel.value;
    const {footage: reels, stage} = foleySources.value;
    const known = [...stage.map(n => `stage:${n}`), ...reels.map(n => `footage:${n}`)];
    foleyReel.value = known.includes(keep) ? keep : '';
}

// Bring your own still: shelve a browser-side file into footage/ and
// return the name it earned there (the server sniffs the bytes and dodges
// collisions, so the name that comes back is the one to pick, not file.name).
export async function shelveStill(file: File): Promise<string> {
    const {shelved} = await api<{shelved: string}>('/api/footage/upload', await readStill(file));
    await loadFootage();
    return shelved;
}

// Cast a still into footage/ and make it the standing lead everywhere.
export async function castAsLead(image: string, from?: string): Promise<string> {
    const {cast} = await api<{cast: string}>('/api/stage/cast', from ? {image, from} : {image});
    forgeLead.value = cast;
    await loadFootage(cast);
    return cast;
}
