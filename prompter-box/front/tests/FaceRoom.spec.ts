import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import FaceRoom from '../src/rooms/FaceRoom.vue';
import {facePrompt, faceSitter} from '../src/stores/booth';

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
    const wrapper = mount(FaceRoom);
    await vi.advanceTimersByTimeAsync(0);
    return wrapper;
};

describe('FaceRoom', () => {
    beforeEach(() => {
        vi.useFakeTimers();
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
