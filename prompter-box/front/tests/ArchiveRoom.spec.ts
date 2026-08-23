import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import ArchiveRoom from '../src/rooms/ArchiveRoom.vue';
import {archive} from '../src/stores/archive';
import {pins} from '../src/stores/pins';

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
        pins.value = [];
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
        // the mount's own take-home pair (Download, Copy image) comes first; the room's act follows
        const act = wrapper.findAll('.mount-acts .act').find(n => n.text() === 'Copy the cue');
        expect(act).toBeDefined();
        if (!act) return;
        await act.trigger('click');
        expect(writeText).toHaveBeenCalledWith('the crier tolls the bell');
        expect(act.text()).toBe('Cue copied');
        vi.unstubAllGlobals();
        wrapper.unmount();
    });

    it('pins a mounted recipe onto the board — settings only, no file-facts (#08)', async () => {
        const hung = {id: 'pin-1', name: 'the crier tolls the bell', room: 'stage',
                      recipe: {prompt: 'the crier tolls the bell', model: 'wan22-i2v-14b', seed: 7}};
        apiMock.mockImplementation((path: string) => {
            if (path === '/api/archive') return Promise.resolve(shelves());
            if (path === '/api/pins/pin') return Promise.resolve({pin: hung});
            if (path === '/api/pins') return Promise.resolve({pins: [hung]});
            return Promise.reject(new Error(`no window: ${path}`));
        });
        const wrapper = mount(ArchiveRoom, {props: {active: true}});
        await vi.advanceTimersByTimeAsync(0);
        await wrapper.find('.canister').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        const pinAct = wrapper.findAll('.mount-acts .act').at(-1);
        if (!pinAct) throw new Error('the Print carries no acts — the pin act never hung');
        expect(pinAct.text()).toBe('Pin this recipe…');
        await pinAct.trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        const naming = wrapper.find('.pin-naming');
        expect(naming.exists()).toBe(true);
        expect((naming.find('input').element as HTMLInputElement).value).toBe('the crier tolls the bell');
        await naming.find('button.fire').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        expect(apiMock).toHaveBeenCalledWith('/api/pins/pin', {
            name: 'the crier tolls the bell', room: 'stage', source: 'crier-toll.mp4',
            recipe: {prompt: 'the crier tolls the bell', model: 'wan22-i2v-14b', seed: 7},
        });
        const board = wrapper.find('#pinboard');
        expect(board.exists()).toBe(true);
        expect(board.text()).toContain('the crier tolls the bell');
        expect(wrapper.find('.pin-naming').exists()).toBe(false);
        wrapper.unmount();
    });
});
