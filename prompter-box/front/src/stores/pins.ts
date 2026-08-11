import {ref} from 'vue';
import {api} from '../composables/useBoothApi';
import type {PinnedRecipe} from '../lib/pins';

// The Pinboard (#08) — named formulas promoted from proven takes. Shared
// because the Canisters hang them and the Kiln, the Night Shift, and the
// Stage all reach for them.
export const pins = ref<PinnedRecipe[]>([]);

export async function loadPins() {
    try {
        pins.value = (await api<{pins: PinnedRecipe[]}>('/api/pins')).pins;
    } catch {
        // the board stays bare — the booth may predate the pinboard
    }
}

export async function hangPin(pin: {name: string; room: string; source?: string; recipe: Record<string, unknown>}) {
    await api('/api/pins/pin', pin);
    await loadPins();
}

export async function takeDownPin(id: string) {
    await api('/api/pins/unpin', {pin_id: id});
    await loadPins();
}

// The hand-off wires — an apply act parks the formula here and opens the
// tab; the room consumes it. Same cross-room cue pattern as booth.ts.
export interface PinHandoff {
    name: string;
    recipe: Record<string, unknown>;
}

export const kilnHandoff = ref<PinHandoff | null>(null);
export const stageHandoff = ref<PinHandoff | null>(null);
