import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import StageRoom from '../src/rooms/StageRoom.vue';
import {leadRes, pickedImage, stagePrompt} from '../src/stores/booth.js';

// The Stage's contract (#00063 Phase 3): the playbill drives the form, the
// wardrobe rides the payload, and every refusal voices the old front's words.

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn()}));
vi.mock('../src/composables/useBoothApi.js', () => ({api: apiMock}));

const MODELS = {
    models: [
        {type: 'i2v_14b', name: 'Wan 2.2 i2v 14B', kind: 'i2v', resolution: '704x1280', video_length: 41,
            steps: 4, guidance: 1, loras: ['fastwan.safetensors', 'detail.safetensors'], note: 'the house recipe'},
        {type: 'scail', name: 'SCAIL-2', kind: 'swap', resolution: '480x832', video_length: 81,
            steps: 20, guidance: 5, loras: []},
        {type: 'krea', name: 'Krea 2', kind: 't2i', resolution: '1024x1024', video_length: 1,
            steps: 28, guidance: 4.5, loras: []},
    ],
    default: 'i2v_14b',
};

const routes = overrides => path => {
    const table = {
        '/api/stage/models': MODELS,
        '/api/stage/job': {state: 'idle'},
        '/api/stage/generate': {ok: true},
        '/api/foley/sources': {footage: ['walk.mp4'], stage: ['take.webm']},
        '/api/archive': {stage: [], face: [], foley: []},
        ...overrides,
    };
    return path in table ? Promise.resolve(table[path]) : Promise.reject(new Error(`no window: ${path}`));
};

const boot = async () => {
    const wrapper = mount(StageRoom);
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(0);
    return wrapper;
};

describe('StageRoom', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        apiMock.mockReset();
        apiMock.mockImplementation(routes());
        stagePrompt.value = '';
        pickedImage.value = null;
        leadRes.value = null;
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('the playbill applies the performer: presets, knobs, wardrobe, note', async () => {
        const wrapper = await boot();
        expect(wrapper.find('#stage-model').element.value).toBe('i2v_14b');
        expect(wrapper.find('#stage-res').element.value).toBe('704x1280');
        expect(wrapper.find('#stage-steps').element.value).toBe('4');
        expect(wrapper.findAll('.garment')).toHaveLength(2);
        expect(wrapper.find('#stage-note').text()).toBe('the house recipe');
        wrapper.unmount();
    });

    it('an i2v cue without a lead is refused in the old voice', async () => {
        const wrapper = await boot();
        await wrapper.find('#stage-go').trigger('click');
        expect(wrapper.find('.error').text()).toBe('The Stage needs a lead — pick a start image from the footage.');
        wrapper.unmount();
    });

    it('a swap cue without choreography names the performer', async () => {
        const wrapper = await boot();
        await wrapper.find('#stage-model').setValue('scail');
        await vi.advanceTimersByTimeAsync(0);
        pickedImage.value = 'crier.png';
        await wrapper.find('#stage-go').trigger('click');
        expect(wrapper.find('.error').text()).toBe('SCAIL-2 needs choreography — pick a driving video.');
        wrapper.unmount();
    });

    it('a donned garment rides the payload with its strength', async () => {
        const wrapper = await boot();
        pickedImage.value = 'crier.png';
        stagePrompt.value = 'the bell swings';
        await wrapper.findAll('.garment button')[0].trigger('click');
        await wrapper.findAll('.garment input')[0].setValue('0.8');
        await wrapper.find('#stage-go').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        expect(apiMock).toHaveBeenCalledWith('/api/stage/generate', expect.objectContaining({
            model_type: 'i2v_14b',
            prompt: 'the bell swings',
            image: 'crier.png',
            resolution: '704x1280',
            video_length: 41,
            loras: ['fastwan.safetensors'],
            lora_multipliers: [0.8],
        }));
        wrapper.unmount();
    });

    it('a cast lead matches the resolution once, then stands down', async () => {
        const wrapper = await boot();
        leadRes.value = {w: 1920, h: 1080};
        await vi.advanceTimersByTimeAsync(0);
        expect(wrapper.find('#stage-res').element.value).toBe('1280x720');
        expect(leadRes.value).toBeNull();
        wrapper.unmount();
    });

    it('a t2i performer swaps frames for strength', async () => {
        const wrapper = await boot();
        await wrapper.find('#stage-model').setValue('krea');
        await vi.advanceTimersByTimeAsync(0);
        expect(wrapper.find('#stage-len-wrap').isVisible()).toBe(false);
        expect(wrapper.find('#stage-strength-wrap').isVisible()).toBe(true);
        wrapper.unmount();
    });
});
