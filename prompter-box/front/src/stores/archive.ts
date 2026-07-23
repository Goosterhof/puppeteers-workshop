import {ref} from 'vue';
import type {Archive} from '../lib/canisters';
import {api} from '../composables/useBoothApi';

// The Canisters' shelves — shared because every room that develops a take
// (Stage, Face Shop, Foley) refreshes the archive when one lands.
export const archive = ref<Archive>({stage: [], face: [], foley: []});

export async function loadArchive() {
    try {
        archive.value = await api<Archive>('/api/archive');
    } catch {
        // the shelves stay dark — the booth may predate the archive window
    }
}
