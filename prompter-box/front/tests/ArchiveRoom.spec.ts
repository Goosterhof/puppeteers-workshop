import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import ArchiveRoom from '../src/rooms/ArchiveRoom.vue';
import {archive} from '../src/stores/archive';

// Chaos #00085 detonation 3: the archive mount is a Print like every fresh
// take — same paper, same chips, the age stamp where Fresh sits.

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn<(path: string, body?: unknown) => Promise<unknown>>()}));
vi.mock('../src/composables/useBoothApi', () => ({api: apiMock}));

const threeHoursAgo = () => Date.now() / 1000 - 3 * 3600;

const shelves = () => ({
    stage: [{name: 'crier-toll.mp4', kind: 'video', mtime: threeHoursAgo(),
             meta: {prompt: 'the crier tolls the bell', model: 'wan22-i2v-14b', seed: 7}}],
    face: [],
    foley: [],
});

describe('ArchiveRoom', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        apiMock.mockReset();
        apiMock.mockImplementation((path: string) => path === '/api/archive'
            ? Promise.resolve(shelves()) : Promise.reject(new Error(`no window: ${path}`)));
        archive.value = {stage: [], face: [], foley: []};
        Element.prototype.scrollIntoView ??= () => {};
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('mounting a canister frames it as a Print with the age stamp where Fresh sits', async () => {
        const wrapper = mount(ArchiveRoom, {props: {active: true}});
        await vi.advanceTimersByTimeAsync(0);

        await wrapper.find('.canister').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        const print = wrapper.find('.mount');
        expect(print.exists()).toBe(true);
        expect(print.find('.mount-stamp').text()).toBe('3 h ago');
        expect(print.text()).toContain('the crier tolls the bell');
        expect(print.text()).toContain('wan22-i2v-14b');
        expect(print.text()).toContain('seed 7');
        wrapper.unmount();
    });

    it('the Print carries the cue-copy act, restamping itself when run', async () => {
        const wrapper = mount(ArchiveRoom, {props: {active: true}});
        await vi.advanceTimersByTimeAsync(0);
        await wrapper.find('.canister').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        const writeText = vi.fn<(text: string) => void>();
        vi.stubGlobal('navigator', {clipboard: {writeText}});
        const act = wrapper.find('.mount-acts .act');
        expect(act.text()).toBe('Copy the cue');
        await act.trigger('click');
        expect(writeText).toHaveBeenCalledWith('the crier tolls the bell');
        expect(wrapper.find('.mount-acts .act').text()).toBe('Cue copied');
        vi.unstubAllGlobals();
        wrapper.unmount();
    });
});
