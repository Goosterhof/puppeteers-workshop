// The Pinboard's pure grammar (#08) — a pin is a named, replayable recipe
// promoted BOTTOM-UP from a proven take. The Canisters record what WAS done;
// a pin marks what SHOULD be repeated. Same store, two intents.

import type {CanisterMeta, Chip} from './canisters';

export type PinRoom = 'stage' | 'face' | 'foley' | 'kiln';

export interface PinnedRecipe {
    id: string;
    name: string;
    room: PinRoom;
    source?: string | null;
    recipe: Record<string, unknown>;
    pinned_at?: string;
}

// The knobs a pin repeats, in the order the chips read best. Prompt rides
// as the card's underline, not a chip — a sentence is not a knob.
const KNOWN: [string, (v: unknown) => string][] = [
    ['model', v => String(v)],
    ['seed', v => `seed ${v}`],
    ['steps', v => `${v} steps`],
    ['guidance', v => `cfg ${v}`],
    ['resolution', v => String(v)],
    ['frames', v => `${v} fr`],
    ['octree', v => `octree ${v}`],
    ['threshold', v => `threshold ${v}`],
];

export function recipeChips(recipe: Record<string, unknown>): Chip[] {
    const chips: Chip[] = [];
    for (const [key, fmt] of KNOWN) {
        if (recipe[key] !== undefined) chips.push([fmt(recipe[key]), 'chip']);
    }
    if (recipe.two_sided) chips.push(['two-sided', 'chip']);
    for (const l of (Array.isArray(recipe.loras) ? recipe.loras : [])) chips.push([`+ ${l}`, 'chip']);
    return chips;
}

// What of a canister's embedded metadata is worth repeating — the settings,
// never the file-facts (age, weight, duration are history, not formula).
export function canisterRecipe(meta: CanisterMeta): Record<string, unknown> {
    const recipe: Record<string, unknown> = {};
    for (const key of ['model', 'seed', 'steps', 'guidance', 'resolution', 'frames', 'loras', 'prompt'] as const) {
        const v = meta[key];
        if (v !== undefined && v !== '' && !(Array.isArray(v) && !v.length)) recipe[key] = v;
    }
    return recipe;
}

// The kiln's reading of a recipe — only the knobs its panel owns, coerced
// the way the panel would have typed them.
export interface KilnKnobs {
    octree?: number;
    threshold?: number;
    seed?: number;
    two_sided?: boolean;
}

export function kilnKnobs(recipe: Record<string, unknown>): KilnKnobs {
    const knobs: KilnKnobs = {};
    if (Number(recipe.octree)) knobs.octree = Number(recipe.octree);
    if (Number(recipe.threshold)) knobs.threshold = Number(recipe.threshold);
    if (recipe.seed !== undefined && recipe.seed !== null && !Number.isNaN(Number(recipe.seed))) {
        knobs.seed = Number(recipe.seed);
    }
    if (recipe.two_sided !== undefined) knobs.two_sided = Boolean(recipe.two_sided);
    return knobs;
}

// Where a pin can be replayed — the apply act's label, per pin. Foley pins
// hang for the record (and the shelf search) but no panel takes them yet,
// and a face pin replays only its prompt — without one there is nothing to
// cue, so it gets no act rather than a live button that no-ops (the
// general's review of PR #14, Minor 1).
const APPLY_LABEL: Record<PinRoom, string> = {
    kiln: '→ Fire with these settings',
    stage: '→ Cue the stage with it',
    face: '→ Cue the face shop with it',
    foley: '',
};

export function applyLabel(pin: PinnedRecipe): string {
    if (pin.room === 'face' && typeof pin.recipe.prompt !== 'string') return '';
    return APPLY_LABEL[pin.room];
}
