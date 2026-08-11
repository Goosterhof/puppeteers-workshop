import {describe, expect, it} from 'vitest';
import {applyLabel, canisterRecipe, kilnKnobs, recipeChips} from '../src/lib/pins';
import type {PinnedRecipe} from '../src/lib/pins';

// The Pinboard's pure grammar (#08) — what of a take is worth repeating,
// how a formula reads as chips, and how the kiln coerces its knobs.

describe('canisterRecipe', () => {
    it('should keep the settings and drop the file-facts', () => {
        expect(canisterRecipe({
            model: 'wan22-i2v-14b', seed: 7, steps: 4, guidance: 1,
            resolution: '704x1280', frames: 41, loras: ['fastwan'],
            prompt: 'the bell swings', duration_s: 2.5,
        })).toStrictEqual({
            model: 'wan22-i2v-14b', seed: 7, steps: 4, guidance: 1,
            resolution: '704x1280', frames: 41, loras: ['fastwan'],
            prompt: 'the bell swings',
        });
    });

    it('should drop empty knobs — a bare wardrobe is not a setting', () => {
        expect(canisterRecipe({prompt: '', loras: [], seed: 0})).toStrictEqual({seed: 0});
    });

    it('should read a bare shelf as an empty formula', () => {
        expect(canisterRecipe({})).toStrictEqual({});
    });
});

describe('recipeChips', () => {
    it('should read the knobs in shelf order and keep the prompt off the chips', () => {
        const chips = recipeChips({
            octree: 224, threshold: 0.4, seed: 7, two_sided: true,
            loras: ['OmniNFT'], prompt: 'a spoked vehicle',
        });
        expect(chips).toStrictEqual([
            ['seed 7', 'chip'],
            ['octree 224', 'chip'],
            ['threshold 0.4', 'chip'],
            ['two-sided', 'chip'],
            ['+ OmniNFT', 'chip'],
        ]);
    });

    it('should stay silent about knobs the formula does not carry', () => {
        expect(recipeChips({steps: 4})).toStrictEqual([['4 steps', 'chip']]);
    });
});

describe('kilnKnobs', () => {
    it('should coerce the panel knobs the way the panel would type them', () => {
        expect(kilnKnobs({octree: '224', threshold: 0.4, seed: 7, two_sided: false, prompt: 'noise'}))
            .toStrictEqual({octree: 224, threshold: 0.4, seed: 7, two_sided: false});
    });

    it('should leave out what the formula does not say', () => {
        expect(kilnKnobs({steps: 4})).toStrictEqual({});
    });
});

describe('applyLabel', () => {
    const pin = (room: PinnedRecipe['room'], recipe: PinnedRecipe['recipe']): PinnedRecipe =>
        ({id: 'pin-1', name: 'x', room, recipe});

    it('should offer no replay act for foley — no panel takes those pins yet', () => {
        expect(applyLabel(pin('foley', {prompt: 'rain on slate'}))).toBe('');
        expect(applyLabel(pin('kiln', {octree: 224}))).not.toBe('');
        expect(applyLabel(pin('stage', {steps: 4}))).not.toBe('');
    });

    it('should offer a face act only when there is a prompt to cue (PR #14 Minor 1)', () => {
        expect(applyLabel(pin('face', {prompt: 'a brass diving helmet'}))).not.toBe('');
        expect(applyLabel(pin('face', {seed: 7}))).toBe('');
    });
});
