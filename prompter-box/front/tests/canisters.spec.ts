import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {age, canisterChips, filterArchive, type Archive, type ShelfItem} from '../src/lib/canisters';

// The Canisters' pure grammar — chips, ages, and the shelf filter — pinned
// to the single-file front's behavior (#00063 Phase 2).

const NOW_S = 1_800_000_000;

describe('age', () => {
    beforeEach(() => {
        vi.spyOn(Date, 'now').mockReturnValue(NOW_S * 1000);
    });
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('speaks the four ages of a canister', () => {
        expect(age(NOW_S - 30)).toBe('just now');
        expect(age(NOW_S - 600)).toBe('10 min ago');
        expect(age(NOW_S - 7200)).toBe('2 h ago');
        expect(age(NOW_S - 259200)).toBe('3 d ago');
    });
});

describe('canisterChips', () => {
    const item = {
        room: 'stage',
        mtime: NOW_S - 30,
        size: 2 * 1048576,
        meta: {model: 'wan22-i2v-14b', seed: 7, steps: 4, guidance: 1, resolution: '704x1280', frames: 41, loras: ['fastwan']},
    } as ShelfItem;

    beforeEach(() => {
        vi.spyOn(Date, 'now').mockReturnValue(NOW_S * 1000);
    });
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('tells the whole recipe, room chip first, age and weight last', () => {
        expect(canisterChips(item)).toStrictEqual([
            ['Stage', 'chip room'],
            ['wan22-i2v-14b', 'chip'],
            ['seed 7', 'chip'],
            ['4 steps', 'chip'],
            ['cfg 1', 'chip'],
            ['704x1280', 'chip'],
            ['41 fr', 'chip'],
            ['+ fastwan', 'chip'],
            ['just now', 'chip'],
            ['2.0 MB', 'chip'],
        ]);
    });

    it('a fresh take wears the stamp instead of an age chip', () => {
        const chips = canisterChips(item, {fresh: true});
        expect(chips.at(-1)).toStrictEqual(['+ fastwan', 'chip']);
    });

    it('seed 0 and cfg 0 still earn their chips', () => {
        const chips = canisterChips({room: 'face', mtime: NOW_S, meta: {seed: 0, guidance: 0}} as ShelfItem, {fresh: true});
        expect(chips).toContainEqual(['seed 0', 'chip']);
        expect(chips).toContainEqual(['cfg 0', 'chip']);
    });
});

describe('filterArchive', () => {
    const archive: Archive = {
        stage: [
            {name: 'crier-seed7.webm', kind: 'video', mtime: 300, meta: {prompt: 'the bell swings'}},
            {name: 'still.png', kind: 'image', mtime: 100, meta: {}},
        ],
        face: [{name: 'portrait.png', kind: 'image', mtime: 200, meta: {seed: 9}}],
        foley: [{name: 'scream.flac', kind: 'audio', mtime: 400, meta: {}}],
    };

    it('unfiltered: every room, newest first', () => {
        expect(filterArchive(archive).map(it => it.name))
            .toStrictEqual(['scream.flac', 'crier-seed7.webm', 'portrait.png', 'still.png']);
    });

    it('room and kind pills narrow the shelves', () => {
        expect(filterArchive(archive, {room: 'stage'}).map(it => it.name))
            .toStrictEqual(['crier-seed7.webm', 'still.png']);
        expect(filterArchive(archive, {kind: 'image'}).map(it => it.name))
            .toStrictEqual(['portrait.png', 'still.png']);
    });

    it('search reads filename AND meta, case-insensitive', () => {
        expect(filterArchive(archive, {search: 'CRIER'}).map(it => it.name)).toStrictEqual(['crier-seed7.webm']);
        expect(filterArchive(archive, {search: 'bell swings'}).map(it => it.name)).toStrictEqual(['crier-seed7.webm']);
        expect(filterArchive(archive, {search: 'seed'}).map(it => it.name))
            .toStrictEqual(['crier-seed7.webm', 'portrait.png']);
    });

    it('every item carries its room home', () => {
        expect(filterArchive(archive, {kind: 'audio'})[0]!.room).toBe('foley');
    });
});
