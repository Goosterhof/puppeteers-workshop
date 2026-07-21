import {ref} from 'vue';
import {api} from '../composables/useBoothApi.js';

// The booth's shared state — the module-global era's cross-room wires
// (forgeLead, pickedImage, faceSitter, the footage shelf, tab navigation)
// gathered into one reactive store (#00063 Phase 2). Plain module-scoped
// refs, no store library: eleven rooms, one booth.

export const activeTab = ref('forge');
export const openTab = name => {
    activeTab.value = name;
};

// The leads: what the Promptsmith looks at, what the Stage starts from,
// what the Face Shop edits.
export const forgeLead = ref(null);
export const pickedImage = ref(null);
export const faceSitter = ref(null);

// A cast lead's natural size, parked for the Stage's resolution matcher —
// consumed when the Stage room rises in Phase 3.
export const leadRes = ref(null);

export const footage = ref([]);
export async function loadFootage(preselect) {
    footage.value = (await api('/api/footage')).images;
    if (preselect) pickedImage.value = preselect;
}

// The Foley Booth's reel shelf — shared so other rooms can preselect a take
// ("Score it in the foley booth →") before opening the tab.
export const foleySources = ref({footage: [], stage: []});
export const foleyReel = ref('');
export async function loadFoleySources(preselect) {
    foleySources.value = await api('/api/foley/sources');
    const keep = preselect ?? foleyReel.value;
    const {footage: reels, stage} = foleySources.value;
    const known = [...stage.map(n => `stage:${n}`), ...reels.map(n => `footage:${n}`)];
    foleyReel.value = known.includes(keep) ? keep : '';
}

// Cast a still into footage/ and make it the standing lead everywhere.
export async function castAsLead(image, from) {
    const {cast} = await api('/api/stage/cast', from ? {image, from} : {image});
    forgeLead.value = cast;
    await loadFootage(cast);
    return cast;
}
