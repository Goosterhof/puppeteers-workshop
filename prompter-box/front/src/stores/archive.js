import {ref} from 'vue';
import {api} from '../composables/useBoothApi.js';

// The Canisters' shelves — shared because every room that develops a take
// (Stage, Face Shop, Foley) refreshes the archive when one lands.
export const archive = ref({stage: [], face: [], foley: []});

export async function loadArchive() {
    try {
        archive.value = await api('/api/archive');
    } catch {
        // the shelves stay dark — the booth may predate the archive window
    }
}
