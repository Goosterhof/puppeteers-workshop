import {beforeEach, describe, expect, it} from 'vitest';
import {readFaceWorkbench, saveFaceWorkbench} from '../src/lib/face-workbench';
import type {FaceWorkbench} from '../src/lib/face-workbench';

const makeBench = (): FaceWorkbench => ({
    original: {room: 'footage', name: 'character.png'},
    selected: null, revisions: [], pending: null,
    draft: {prompt: 'a wicked grin', source: 'character.png', width: 768, height: 1024, seed: 0, model: 'klein'},
});
describe('the saved character bench', () => {
    beforeEach(() => localStorage.clear());
    it('refuses damaged tracking data instead of submitting an uncertain job', () => {
        const w = makeBench();
        saveFaceWorkbench(w);
        const raw = localStorage.getItem('workshop-face-workbench-v1')!;
        localStorage.setItem('workshop-face-workbench-v1', raw.replace('"pending":null', '"pending":{"id":23}'));
        expect(readFaceWorkbench()).toBeNull();
        localStorage.setItem('workshop-face-workbench-v1', '{broken');
        expect(readFaceWorkbench()).toBeNull();
    });
    it('bounds the revision strip while retaining the original and zero seed', () => {
        const w = makeBench();
        w.revisions = Array.from({length: 60}, (_, i) => ({name: `version-${i}.png`, recipe: {...w.draft}, source: w.original}));
        saveFaceWorkbench(w);
        const recovered = readFaceWorkbench()!;
        expect(recovered.revisions).toHaveLength(40);
        expect(recovered.revisions[0]!.name).toBe('version-20.png');
        expect(recovered.original).toStrictEqual(w.original);
        expect(recovered.draft.seed).toBe(0);
    });
});
