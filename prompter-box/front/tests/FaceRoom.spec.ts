import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import FaceRoom from '../src/rooms/FaceRoom.vue';
import {faceRecipeHandoff} from '../src/stores/pins';
import {activeTab, faceHandoff, facePrompt, faceSitter, forgeLead, pickedImage, refineStill, stagePrompt} from '../src/stores/booth';

// The Face Shop's contract (#00063 Phase 3): the sitter flips the room into
// EDIT mode, the poll speaks 'painting', and a rejection names the brush.

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn<(path: string, body?: unknown) => Promise<unknown>>()}));
vi.mock('../src/composables/useBoothApi', () => ({api: apiMock}));

const routes = (overrides: Record<string, unknown> = {}) => (path: string): Promise<unknown> => {
    const table: Record<string, unknown> = {
        '/api/face/models': {painters: ['flux-2-klein-9b.gguf', 'flux-2-dev.gguf'], default: 'flux-2-klein-9b.gguf'},
        '/api/face/generate': {prompt_id: 'p1'},
        '/api/face/result/p1': {state: 'painting'},
        '/api/archive': {stage: [], face: [], foley: []},
        ...overrides,
    };
    return path in table ? Promise.resolve(table[path]) : Promise.reject(new Error(`no window: ${path}`));
};

const boot = async () => {
    activeTab.value = 'face';
    const wrapper = mount(FaceRoom);
    await vi.advanceTimersByTimeAsync(0);
    return wrapper;
};

describe('FaceRoom', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        localStorage.clear();
        faceHandoff.value = null;
        faceRecipeHandoff.value = null;
        apiMock.mockReset();
        apiMock.mockImplementation(routes());
        facePrompt.value = '';
        faceSitter.value = null;
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('a sitter locks width and height — the output follows the sitter', async () => {
        const wrapper = await boot();
        expect(wrapper.find<HTMLInputElement>('#face-w').element.disabled).toBe(false);
        faceSitter.value = 'crier.png';
        await vi.advanceTimersByTimeAsync(0);
        expect(wrapper.find<HTMLInputElement>('#face-w').element.disabled).toBe(true);
        expect(wrapper.find<HTMLInputElement>('#face-h').element.disabled).toBe(true);
        wrapper.unmount();
    });

    it('the cue carries painter, dimensions, and the sitter as source', async () => {
        const wrapper = await boot();
        facePrompt.value = 'repaint him as a night watchman';
        faceSitter.value = 'crier.png';
        await vi.advanceTimersByTimeAsync(0);
        await wrapper.find('#face-go').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        expect(apiMock).toHaveBeenCalledWith('/api/face/generate', {
            prompt: 'repaint him as a night watchman',
            width: 768, height: 1024, seed: 7,
            model: 'flux-2-klein-9b.gguf',
            source: 'crier.png',
        });
        expect(wrapper.find<HTMLButtonElement>('#face-go').element.disabled).toBe(true);
        wrapper.unmount();
    });

    it('a done paint hangs the Prints with the cued recipe, extension stripped', async () => {
        const wrapper = await boot();
        facePrompt.value = 'a pizza box';
        await wrapper.find('#face-go').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'done', images: ['out.png']}}));
        await vi.advanceTimersByTimeAsync(1500);
        await vi.advanceTimersByTimeAsync(0);

        const mountEl = wrapper.find('.mount');
        expect(mountEl.exists()).toBe(true);
        expect(mountEl.text()).toContain('a pizza box');
        expect(mountEl.text()).toContain('flux-2-klein-9b');
        expect(mountEl.text()).not.toContain('.gguf');
        expect(wrapper.find<HTMLButtonElement>('#face-go').element.disabled).toBe(false);
        wrapper.unmount();
    });

    it('a rejection names the broken brush from the ComfyUI detail pairs', async () => {
        const wrapper = await boot();
        await wrapper.find('#face-go').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        apiMock.mockImplementation(routes({
            '/api/face/result/p1': {state: 'failed', detail: [
                ['execution_error', {node_type: 'KSampler', exception_message: 'out of memory'}],
            ]},
        }));
        await vi.advanceTimersByTimeAsync(1500);
        await vi.advanceTimersByTimeAsync(0);

        expect(wrapper.find('.error').text()).toContain('the broken brush:\nKSampler: out of memory');
        wrapper.unmount();
    });
});

// The character loop must retain the source that was actually cued, keep
// earlier versions, and observe an interrupted job rather than firing it twice.
describe('FaceRoom — the character refinement loop', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        localStorage.clear();
        faceHandoff.value = null;
        faceRecipeHandoff.value = null;
        apiMock.mockReset();
        apiMock.mockImplementation(routes({
            '/api/stage/cast': {cast: 'out-2.png'},
            '/api/footage': {images: ['crier.png', 'out-2.png']},
        }));
        facePrompt.value = '';
        faceSitter.value = 'crier.png';
    });
    afterEach(() => vi.useRealTimers());

    it('captures the source and cue, keeps the previous painting, and can branch from the original', async () => {
        const wrapper = await boot();
        facePrompt.value = 'sharpen the grin';
        await wrapper.find('#face-go').trigger('click');
        facePrompt.value = 'a future change';
        apiMock.mockImplementation(routes({
            '/api/face/result/p1': {state: 'done', images: ['out.png']},
            '/api/stage/cast': {cast: 'out-2.png'},
            '/api/footage': {images: ['crier.png', 'out-2.png']},
        }));
        await vi.advanceTimersByTimeAsync(1500);
        expect(wrapper.find('.mount-title').text()).toBe('sharpen the grin');
        expect(wrapper.find('.comparison-reference img').attributes('src')).toBe('/footage/crier.png');
        await wrapper.findAll('.mount-acts button').find(b => b.text() === 'Refine this version →')!.trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(faceSitter.value).toBe('out-2.png');
        expect(facePrompt.value).toBe('');
        expect(wrapper.findAll('.revision-strip .revision')).toHaveLength(2);
        await wrapper.find('.revision.original').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(faceSitter.value).toBe('crier.png');
        expect(wrapper.findAll('.revision-strip .revision')).toHaveLength(2);
        wrapper.unmount();
    });

    it('reconnects after refresh with the cued recipe and never submits a second painting', async () => {
        let wrapper = await boot();
        facePrompt.value = 'make the smile wicked';
        await wrapper.find('#face-go').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        wrapper.unmount();
        facePrompt.value = '';
        faceSitter.value = null;
        apiMock.mockClear();
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'done', images: ['recovered.png']}}));
        wrapper = await boot();
        await vi.advanceTimersByTimeAsync(1500);
        expect(wrapper.find('.mount-title').text()).toBe('make the smile wicked');
        expect(wrapper.find('.comparison-reference img').attributes('src')).toBe('/footage/crier.png');
        expect(apiMock.mock.calls.some(([path]) => path === '/api/face/generate')).toBe(false);
        wrapper.unmount();
    });

    it('a failed second refinement leaves the successful first version on the bench', async () => {
        const wrapper = await boot();
        facePrompt.value = 'first change';
        await wrapper.find('#face-go').trigger('click');
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'done', images: ['first.png']}}));
        await vi.advanceTimersByTimeAsync(1500);
        facePrompt.value = 'second change';
        await wrapper.find('#face-go').trigger('click');
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'failed', detail: []}}));
        await vi.advanceTimersByTimeAsync(1500);
        expect(wrapper.find('.mount-title').text()).toBe('first change');
        expect(wrapper.find('.error').text()).toContain('earlier versions remain');
        wrapper.unmount();
    });

    it('a current-thumb click preserves the character lineage; a new bench asks before clearing it', async () => {
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'done', images: ['first.png']}}));
        const w = await boot();
        facePrompt.value = 'first change';
        await w.get('#face-go').trigger('click');
        await vi.advanceTimersByTimeAsync(1500);
        w.findComponent({name: 'ThumbRow'}).vm.$emit('pick', 'crier.png');
        await vi.advanceTimersByTimeAsync(0);
        expect(w.findAll('.revision')).toHaveLength(2);
        await w.findAll('.task-picks button').find(b => b.text() === 'Create a new still')!.trigger('click');
        expect(w.get<HTMLDialogElement>('#face-new-dialog').element.open).toBe(true);
        expect(w.findAll('.revision')).toHaveLength(2);
        await w.findAll('dialog button').find(b => b.text() === 'Keep this character')!.trigger('click');
        expect(w.findAll('.revision')).toHaveLength(2);
        await w.findAll('.task-picks button').find(b => b.text() === 'Create a new still')!.trigger('click');
        await w.get('#face-new-confirm').trigger('click');
        expect(w.findAll('.revision')).toHaveLength(0);
        expect(faceSitter.value).toBeNull();
        w.unmount();
    });

    it('a disappeared job after refresh settles as lost, releases the bench, and keeps earlier versions', async () => {
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'done', images: ['first.png']}}));
        let w = await boot();
        facePrompt.value = 'first change';
        await w.get('#face-go').trigger('click');
        await vi.advanceTimersByTimeAsync(1500);
        facePrompt.value = 'second change';
        await w.get('#face-go').trigger('click');
        w.unmount();
        faceSitter.value = null;
        facePrompt.value = '';
        apiMock.mockClear();
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'lost'}}));
        w = await boot();
        await vi.advanceTimersByTimeAsync(1500);
        expect(w.get('.mount-title').text()).toBe('first change');
        expect(w.get('.error').text()).toContain('absent from its queue and history');
        expect(w.get<HTMLButtonElement>('#face-go').element.disabled).toBe(false);
        expect(w.find('#face-abandon').exists()).toBe(false);
        expect(apiMock.mock.calls.some(([path]) => path === '/api/face/generate')).toBe(false);
        w.unmount();
    });

    it('abandonment releases a dark painting without dropping versions or letting a late poll overwrite them', async () => {
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'done', images: ['first.png']}}));
        let w = await boot();
        facePrompt.value = 'first change';
        await w.get('#face-go').trigger('click');
        await vi.advanceTimersByTimeAsync(1500);
        facePrompt.value = 'second change';
        await w.get('#face-go').trigger('click');
        apiMock.mockImplementation(path => path.startsWith('/api/face/result/')
            ? Promise.reject(new Error('ComfyUI is dark')) : routes()(path));
        await vi.advanceTimersByTimeAsync(4500);
        expect(w.get<HTMLButtonElement>('#face-go').element.disabled).toBe(true);
        expect(w.text()).toContain('Reconnect to the painting');
        let settle!: (job: unknown) => void;
        apiMock.mockImplementation(path => path.startsWith('/api/face/result/')
            ? new Promise(resolve => { settle = resolve; }) : routes()(path));
        await w.findAll('button').find(b => b.text() === 'Reconnect to the painting')!.trigger('click');
        await vi.advanceTimersByTimeAsync(1500);
        await w.get('#face-abandon').trigger('click');
        settle({state: 'done', images: ['abandoned.png']});
        await vi.advanceTimersByTimeAsync(0);
        expect(w.get('.mount-title').text()).toBe('first change');
        expect(w.get<HTMLButtonElement>('#face-go').element.disabled).toBe(false);
        expect(w.findAll('.revision')).toHaveLength(2);
        w.unmount();
        faceSitter.value = null;
        facePrompt.value = '';
        w = await boot();
        expect(w.find('#face-abandon').exists()).toBe(false);
        expect(w.get<HTMLButtonElement>('#face-go').element.disabled).toBe(false);
        expect(w.findAll('.revision')).toHaveLength(2);
        w.unmount();
    });

    it('refining a Stage painting preserves Stage selections and does not name its performer as a Face painter', async () => {
        pickedImage.value = 'stage-character.png';
        forgeLead.value = 'forge-character.png';
        stagePrompt.value = 'keep this motion cue';
        apiMock.mockImplementation(routes({'/api/stage/cast': {cast: 'stage-still.png'}, '/api/footage': {images: ['stage-still.png']}}));
        const w = await boot();
        await refineStill({room: 'stage', name: 'painting.png'}, {model: 'Krea 2', seed: 0});
        await vi.advanceTimersByTimeAsync(0);
        expect(faceSitter.value).toBe('stage-still.png');
        expect(pickedImage.value).toBe('stage-character.png');
        expect(forgeLead.value).toBe('forge-character.png');
        expect(stagePrompt.value).toBe('keep this motion cue');
        expect(w.text()).not.toContain('painter “Krea 2” is absent');
        expect(w.get<HTMLInputElement>('#face-seed').element.value).toBe('0');
        w.unmount();
    });

    it('an incoming character waits for the painting and the Face tab before asking to replace its completed lineage', async () => {
        const w = await boot();
        facePrompt.value = 'the current character';
        await w.get('#face-go').trigger('click');
        await refineStill({room: 'footage', name: 'different.png'}, {}, false, 'the next character');
        await vi.advanceTimersByTimeAsync(0);
        expect(faceSitter.value).toBe('crier.png');
        expect(facePrompt.value).toBe('the current character');
        expect(w.get<HTMLDialogElement>('#face-new-dialog').element.open).toBe(false);
        activeTab.value = 'archive';
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'done', images: ['first.png']}}));
        await vi.advanceTimersByTimeAsync(1500);
        expect(w.get<HTMLDialogElement>('#face-new-dialog').element.open).toBe(false);
        expect(faceHandoff.value?.source).toBe('different.png');
        activeTab.value = 'face';
        await vi.advanceTimersByTimeAsync(0);
        expect(w.get<HTMLDialogElement>('#face-new-dialog').element.open).toBe(true);
        expect(w.get('.mount-title').text()).toBe('the current character');
        expect(w.get('.comparison-reference img').attributes('src')).toBe('/footage/crier.png');
        await w.findAll('dialog button').find(b => b.text() === 'Keep this character')!.trigger('click');
        expect(faceSitter.value).toBe('crier.png');
        expect(facePrompt.value).toBe('the current character');
        expect(w.findAll('.revision')).toHaveLength(2);
        await refineStill({room: 'footage', name: 'different.png'}, {seed: 0}, false, 'the next character');
        await vi.advanceTimersByTimeAsync(0);
        await w.get('#face-new-confirm').trigger('click');
        expect(faceSitter.value).toBe('different.png');
        expect(facePrompt.value).toBe('the next character');
        expect(w.findAll('.revision')).toHaveLength(1);
        expect(w.get<HTMLInputElement>('#face-seed').element.value).toBe('0');
        w.unmount();
    });

    it('a queued handoff without confirmation preserves a cue edited during the wait', async () => {
        const w = await boot();
        facePrompt.value = 'the running change';
        await w.get('#face-go').trigger('click');
        await refineStill({room: 'footage', name: 'crier.png'}, {}, true);
        facePrompt.value = 'the next change typed while waiting';
        activeTab.value = 'stage';
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'done', images: ['first.png']}}));
        await vi.advanceTimersByTimeAsync(1500);
        activeTab.value = 'face';
        await vi.advanceTimersByTimeAsync(0);
        expect(faceHandoff.value).toBeNull();
        expect(facePrompt.value).toBe('the next change typed while waiting');
        expect(w.get<HTMLDialogElement>('#face-new-dialog').element.open).toBe(false);
        expect(w.get('.mount-title').text()).toBe('the running change');
        w.unmount();
    });

    it('animating a character keeps the motion cue already on Stage', async () => {
        stagePrompt.value = 'a measured bow';
        apiMock.mockImplementation(routes({'/api/face/result/p1': {state: 'done', images: ['first.png']}, '/api/stage/cast': {cast: 'first.png'}, '/api/footage': {images: ['first.png']}}));
        const w = await boot();
        facePrompt.value = 'a sharper grin';
        await w.get('#face-go').trigger('click');
        await vi.advanceTimersByTimeAsync(1500);
        await w.findAll('.mount-acts button').find(b => b.text() === 'Animate this version →')!.trigger('click');
        expect(stagePrompt.value).toBe('a measured bow');
        w.unmount();
    });
});


describe('FaceRoom — proven recipe replay', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        localStorage.clear();
        facePrompt.value = '';
        faceSitter.value = null;
        faceHandoff.value = null;
        apiMock.mockReset();
        apiMock.mockImplementation(routes());
        faceRecipeHandoff.value = {name: 'A proven grin', recipe: {
            prompt: 'a challenging grin', model: 'flux-2-dev', seed: 0, resolution: '1024x768',
        }};
    });
    afterEach(() => vi.useRealTimers());
    it.each(['failed', 'empty'])('restores the recipe even when the painter roster is %s, and can match it on retry', async failure => {
        apiMock.mockImplementation(path => path === '/api/face/models'
            ? failure === 'failed' ? Promise.reject(new Error('dark')) : Promise.resolve({painters: []}) : routes()(path));
        const w = await boot();
        expect(facePrompt.value).toBe('a challenging grin');
        expect(w.get<HTMLInputElement>('#face-w').element.value).toBe('1024');
        expect(w.get<HTMLInputElement>('#face-seed').element.value).toBe('0');
        expect(faceRecipeHandoff.value).toBeNull();
        w.unmount();
    });
    it('a roster retry matches the requested painter without losing the restored cue', async () => {
        apiMock.mockImplementation(path => path === '/api/face/models' ? Promise.reject(new Error('dark')) : routes()(path));
        const w = await boot();
        apiMock.mockImplementation(routes());
        await w.findAll('button').find(b => b.text() === 'Retry painter list')!.trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        await w.get('#face-go').trigger('click');
        expect(apiMock).toHaveBeenCalledWith('/api/face/generate', expect.objectContaining({model: 'flux-2-dev.gguf', seed: 0, prompt: 'a challenging grin'}));
        w.unmount();
    });
    it('a repeated missing painter reports its absence for each recipe, and a later model-free recipe cancels it', async () => {
        const w = await boot();
        faceRecipeHandoff.value = {name: 'Missing first', recipe: {prompt: 'first', model: 'absent'}};
        await vi.advanceTimersByTimeAsync(0);
        expect(w.text()).toContain('painter “absent” is absent');
        faceRecipeHandoff.value = {name: 'Missing again', recipe: {prompt: 'second', model: 'absent'}};
        await vi.advanceTimersByTimeAsync(0);
        expect(w.text()).toContain('painter “absent” is absent');
        faceRecipeHandoff.value = {name: 'Only a cue', recipe: {prompt: 'third', seed: 0}};
        await vi.advanceTimersByTimeAsync(0);
        expect(w.text()).not.toContain('painter “absent” is absent');
        w.unmount();
    });

    it('a model-free recipe cancels the earlier painter request before an outage retry', async () => {
        apiMock.mockImplementation(path => path === '/api/face/models' ? Promise.reject(new Error('dark')) : routes()(path));
        const w = await boot();
        faceRecipeHandoff.value = {name: 'Only a cue', recipe: {prompt: 'the later cue', seed: 0}};
        await vi.advanceTimersByTimeAsync(0);
        apiMock.mockImplementation(routes());
        await w.findAll('button').find(b => b.text() === 'Retry painter list')!.trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        await w.get('#face-go').trigger('click');
        expect(apiMock).toHaveBeenCalledWith('/api/face/generate', expect.objectContaining({model: 'flux-2-klein-9b.gguf', prompt: 'the later cue', seed: 0}));
        w.unmount();
    });

    it('a character handoff reaches the easel even when its model roster is dark', async () => {
        faceRecipeHandoff.value = null;
        faceHandoff.value = {asset: {room: 'face', name: 'original.png'}, source: 'original-copy.png', recipe: {seed: 0}, keepHistory: false};
        apiMock.mockImplementation(path => path === '/api/face/models' ? Promise.reject(new Error('dark')) : routes()(path));
        const w = await boot();
        expect(faceHandoff.value).toBeNull();
        expect(faceSitter.value).toBe('original-copy.png');
        expect(w.get('.character-source img').attributes('src')).toBe('/footage/original-copy.png');
        expect(w.get<HTMLInputElement>('#face-seed').element.value).toBe('0');
        w.unmount();
    });
    it('waits for the storeroom then restores painter, dimensions and zero seed together', async () => {
        const wrapper = await boot();
        await vi.advanceTimersByTimeAsync(0);
        await wrapper.find('#face-go').trigger('click');
        expect(apiMock).toHaveBeenCalledWith('/api/face/generate', {
            prompt: 'a challenging grin', width: 1024, height: 768, seed: 0,
            model: 'flux-2-dev.gguf', source: undefined,
        });
        expect(faceRecipeHandoff.value).toBeNull();
        wrapper.unmount();
    });
});
