import {describe, expect, it} from 'vitest';
import {shelfGroups} from '../src/lib/shelf-groups';

describe('shelfGroups', () => {
    it('puts the none entry headerless on top, then stage takes, then footage — ids unchanged', () => {
        const groups = shelfGroups('— none —', {stage: ['take.webm'], footage: ['walk.mp4', 'run.mp4']});

        expect(groups.map(g => [g.text, g.header ?? true])).toStrictEqual([['', false], ['stage takes', true], ['footage', true]]);
        expect(groups.flatMap(g => g.options.map(o => o.id))).toStrictEqual(['', 'stage:take.webm', 'footage:walk.mp4', 'footage:run.mp4']);
        expect(groups[1]!.options[0]).toStrictEqual({id: 'stage:take.webm', label: 'stage · take.webm', name: 'take.webm'});
        expect(groups[0]!.options[0]).toStrictEqual({id: '', label: '— none —', name: '— none —'});
    });

    it('an empty shelf leaves an empty group, which GroupSelect renders as nothing', () => {
        const groups = shelfGroups('— none —', {stage: [], footage: []});

        expect(groups.map(g => g.options.length)).toStrictEqual([1, 0, 0]);
    });
});
