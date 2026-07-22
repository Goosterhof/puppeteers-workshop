import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

// The Foley Booth's two job paths (#00063 Phase 2 acceptance): a bare cue is
// pure text-to-audio; a picked reel scores the video and the result mounts
// as a Print.

import FoleyRoom from '../src/rooms/FoleyRoom.vue';
import {foleyReel} from '../src/stores/booth.js';

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn()}));
vi.mock('../src/composables/useBoothApi.js', () => ({api: apiMock}));

const routes = overrides => path => {
    const table = {
        '/api/foley/sources': {footage: ['clip.mp4'], stage: ['take-seed7.webm']},
        '/api/foley/job': {state: 'idle'},
        '/api/foley/generate': {ok: true},
        '/api/archive': {stage: [], face: [], foley: []},
        ...overrides,
    };
    return path in table ? Promise.resolve(table[path]) : Promise.reject(new Error(`no window: ${path}`));
};

const fire = async wrapper => {
    await wrapper.find('#foley-go').trigger('click');
    await vi.advanceTimersByTimeAsync(0);
};

describe('FoleyRoom', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        foleyReel.value = '';
        apiMock.mockReset();
        apiMock.mockImplementation(routes());
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('a bare cue fires pure text-to-audio — no reel, no video_from', async () => {
        const wrapper = mount(FoleyRoom);
        await vi.advanceTimersByTimeAsync(0);
        await wrapper.find('#foley-prompt').setValue('a bell rings once');
        await fire(wrapper);

        expect(apiMock).toHaveBeenCalledWith('/api/foley/generate', {
            prompt: 'a bell rings once',
            negative_prompt: 'music, background music, melody',
            duration: 8,
            seed: 7,
            video: '',
            video_from: undefined,
        });
        wrapper.unmount();
    });

    it('a picked reel fires video-to-audio — the stage take rides video/video_from', async () => {
        const wrapper = mount(FoleyRoom);
        await vi.advanceTimersByTimeAsync(0);
        // the reel shelf is a ui-inputs SingleSelect — open, then commit
        await wrapper.find('#foley-video').trigger('click');
        await wrapper.findAll('.ui-select__option').find(o => o.text() === 'stage · take-seed7.webm').trigger('click');
        await wrapper.find('#foley-prompt').setValue('the bell scores itself');
        await fire(wrapper);

        expect(apiMock).toHaveBeenCalledWith('/api/foley/generate', expect.objectContaining({
            video: 'take-seed7.webm',
            video_from: 'stage',
        }));
        wrapper.unmount();
    });

    it('a done job mounts its outputs as Prints — the composite as a reel, the flac as audio', async () => {
        const wrapper = mount(FoleyRoom);
        await vi.advanceTimersByTimeAsync(0);
        await wrapper.find('#foley-prompt').setValue('scream');
        await fire(wrapper);

        apiMock.mockImplementation(routes({
            '/api/foley/job': {state: 'done', seed: 7, outputs: ['scream.flac', 'scream.mp4']},
        }));
        await vi.advanceTimersByTimeAsync(3000);
        await vi.advanceTimersByTimeAsync(0);

        const mounts = wrapper.findAll('.mount');
        expect(mounts).toHaveLength(2);
        expect(mounts[0].find('audio').exists()).toBe(true);
        expect(mounts[1].find('video').exists()).toBe(true);
        expect(mounts[1].text()).toContain('the composite: sound on the frames');
        wrapper.unmount();
    });

    it('a collapsed score voices the exit code in place', async () => {
        const wrapper = mount(FoleyRoom);
        await vi.advanceTimersByTimeAsync(0);
        await fire(wrapper);

        apiMock.mockImplementation(routes({'/api/foley/job': {state: 'failed', exit_code: 1}}));
        await vi.advanceTimersByTimeAsync(3000);
        await vi.advanceTimersByTimeAsync(0);

        expect(wrapper.find('.error').text()).toContain('The score collapsed (exit 1)');
        wrapper.unmount();
    });
});
