import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import StageRoom from '../src/rooms/StageRoom.vue';
import KilnRoom from '../src/rooms/KilnRoom.vue';
import NightShiftRoom from '../src/rooms/NightShiftRoom.vue';
import {pickedImage, stagePrompt} from '../src/stores/booth';
import {kilnHandoff, pins, stageHandoff} from '../src/stores/pins';

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn<(path: string, body?: unknown) => Promise<unknown>>()}));
vi.mock('../src/composables/useBoothApi', () => ({api: apiMock}));
const recipe = {octree: 224, threshold: 0.4, seed: 0, two_sided: true};
const formula = {id: 'proven', name: 'Spoked vehicle', room: 'kiln' as const, recipe};

beforeEach(() => {
    vi.useFakeTimers();
    kilnHandoff.value = null;
    stageHandoff.value = null;
    pins.value = [];
    pickedImage.value = 'character.png';
    stagePrompt.value = '';
    apiMock.mockReset();
    apiMock.mockImplementation(async path => {
        if (path === '/api/stage/models') return {models: [{type: 'house', name: 'House', kind: 'i2v', resolution: '704x1280', video_length: 41, steps: 4, guidance: 1, loras: ['fastwan.safetensors']}], default: 'house'};
        if (path === '/api/pins') return {pins: [formula]};
        if (path === '/api/queue/list') return {rows: [], shift: {running: false}};
        return {state: 'idle', ok: true};
    });
});
afterEach(() => vi.useRealTimers());

describe('proven recipes reach the machines', () => {
    it('a Stage pin arriving before the playbill overrides house defaults, including zero seed/guidance', async () => {
        stageHandoff.value = {name: 'Proven motion', recipe: {model: 'house', prompt: 'the bell swings', steps: 8, guidance: 0, seed: 0, resolution: '1280x720', frames: 81, loras: ['fastwan.safetensors']}};
        const w = mount(StageRoom);
        await vi.advanceTimersByTimeAsync(0);
        await w.get('#stage-go').trigger('click');
        expect(apiMock).toHaveBeenCalledWith('/api/stage/generate', expect.objectContaining({steps: 8, guidance: 0, seed: 0, resolution: '1280x720', video_length: 81, prompt: 'the bell swings', loras: ['fastwan.safetensors']}));
        expect(stageHandoff.value).toBeNull();
        w.unmount();
    });
    it('a Kiln pin restores the firing knobs and zero seed rather than rolling new dice', async () => {
        kilnHandoff.value = {name: 'Spoked vehicle', recipe};
        const w = mount(KilnRoom);
        await vi.advanceTimersByTimeAsync(0);
        await w.get('#kiln-subject').setValue('a bicycle');
        await w.get('#kiln-go').trigger('click');
        expect(apiMock).toHaveBeenCalledWith('/api/kiln/generate', {subject: 'a bicycle', ...recipe});
        expect(kilnHandoff.value).toBeNull();
        w.unmount();
    });
    it('a Night Shift formula dresses a real queue row rather than just changing its label', async () => {
        const w = mount(NightShiftRoom, {props: {active: true}});
        await vi.advanceTimersByTimeAsync(0);
        await w.get('#shift-formula').trigger('click');
        await w.findAll('.ui-select__option').find(o => o.text() === 'Spoked vehicle')!.trigger('click');
        await w.get('#shift-subject').setValue('a bicycle');
        await w.get('#shift-add').trigger('click');
        expect(apiMock).toHaveBeenCalledWith('/api/queue/add', {subject: 'a bicycle', variant_count: 1, job_type: 'kiln', ...recipe});
        w.unmount();
    });
});
