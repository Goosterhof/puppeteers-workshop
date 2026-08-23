import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import StampedMount from '../src/components/StampedMount.vue';
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

// The Light Table walks a FILTERED list, newest first — three prints is
// enough to have a middle, an end, and a place to fall back to.
const three = () => ({
    stage: [
        {name: 'a.png', kind: 'image', mtime: Date.now() / 1000 - 100, meta: {prompt: 'the first'}},
        {name: 'b.png', kind: 'image', mtime: Date.now() / 1000 - 200, meta: {prompt: 'the second'}},
        {name: 'c.png', kind: 'image', mtime: Date.now() / 1000 - 300, meta: {prompt: 'the third'}},
    ],
    face: [],
    foley: [],
});

const press = (key: string, on: EventTarget = document) =>
    on.dispatchEvent(new KeyboardEvent('keydown', {key, bubbles: true, cancelable: true}));

const onBench = (w: ReturnType<typeof mount>) => w.find('.canister[aria-current="true"]')
    .attributes('data-canister');

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

// ===== The Light Table (2026-08-23) =====
// R0 is the whole point of the room: mounting a canister may never scroll the
// deck. These specs are structurally blind to how it LOOKS — the sticky bench
// and both widths are verified by rendering (Pattern 032) — but they can hold
// the grammar: the walk, the escape, the mount-next rule after a bin.

const openRoom = async () => {
    const wrapper = mount(ArchiveRoom, {props: {active: true}, attachTo: document.body});
    await vi.advanceTimersByTimeAsync(0);
    return wrapper;
};

describe('ArchiveRoom — The Light Table', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        apiMock.mockReset();
        apiMock.mockImplementation((path: string) => path === '/api/archive'
            ? Promise.resolve(three()) : Promise.reject(new Error(`no window: ${path}`)));
        archive.value = {stage: [], face: [], foley: []};
        pins.value = [];
        Element.prototype.scrollIntoView ??= () => {};
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('mounting a canister never scrolls the deck — R0, the defect this room exists to kill', async () => {
        const wrapper = await openRoom();
        const scrolled = vi.spyOn(Element.prototype, 'scrollIntoView');

        await wrapper.findAll('.canister')[1]!.trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        expect(wrapper.find('.mount').exists()).toBe(true);
        expect(scrolled).not.toHaveBeenCalled();
        scrolled.mockRestore();
        wrapper.unmount();
    });

    it('← and → walk the filtered list order and stop dead at both ends', async () => {
        const wrapper = await openRoom();

        press('ArrowRight');
        await vi.advanceTimersByTimeAsync(0);
        expect(onBench(wrapper)).toBe('stage/a.png');

        press('ArrowRight');
        await vi.advanceTimersByTimeAsync(0);
        expect(onBench(wrapper)).toBe('stage/b.png');

        press('ArrowLeft');
        press('ArrowLeft');
        await vi.advanceTimersByTimeAsync(0);
        expect(onBench(wrapper)).toBe('stage/a.png');

        // no wrap — wrapping a 193-item triage list loses your place
        press('ArrowLeft');
        await vi.advanceTimersByTimeAsync(0);
        expect(onBench(wrapper)).toBe('stage/a.png');

        press('End');
        await vi.advanceTimersByTimeAsync(0);
        expect(onBench(wrapper)).toBe('stage/c.png');

        press('ArrowDown');
        await vi.advanceTimersByTimeAsync(0);
        expect(onBench(wrapper)).toBe('stage/c.png');
        wrapper.unmount();
    });

    it('Esc puts the print down, and / calls the search field back', async () => {
        const wrapper = await openRoom();
        press('ArrowRight');
        await vi.advanceTimersByTimeAsync(0);
        expect(wrapper.find('.mount').exists()).toBe(true);

        press('Escape');
        await vi.advanceTimersByTimeAsync(0);
        expect(wrapper.find('.mount').exists()).toBe(false);

        press('/');
        expect(document.activeElement).toBe(wrapper.find('#arch-search').element);
        wrapper.unmount();
    });

    it('every binding but Esc is inert while the investor is typing', async () => {
        const wrapper = await openRoom();
        const field = wrapper.find('#arch-search').element;

        press('ArrowRight', field);
        await vi.advanceTimersByTimeAsync(0);
        expect(wrapper.find('.mount').exists()).toBe(false);

        // Esc in the field clears the text first, and leaves the bench alone
        await wrapper.find('#arch-search').setValue('the second');
        await vi.advanceTimersByTimeAsync(0);
        expect(wrapper.findAll('.canister')).toHaveLength(1);
        press('Escape', field);
        await vi.advanceTimersByTimeAsync(0);
        expect(wrapper.findAll('.canister')).toHaveLength(3);
        wrapper.unmount();
    });

    it('after a bin the shelf hands over the print that slid into the gap — down the shelf', async () => {
        const wrapper = await openRoom();
        await wrapper.findAll('.canister')[0]!.trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        // the mount bins the file and reloads the shelves ITSELF, then emits —
        // so by the time the room hears `binned`, the victim is already gone
        archive.value = {...archive.value, stage: archive.value.stage!.slice(1)};
        wrapper.findComponent(StampedMount).vm.$emit('binned', '/stage-output/a.png');
        await vi.advanceTimersByTimeAsync(0);

        expect(onBench(wrapper)).toBe('stage/b.png');
        wrapper.unmount();
    });

    it('binning the last canister on the shelf falls back up one', async () => {
        const wrapper = await openRoom();
        press('End');
        await vi.advanceTimersByTimeAsync(0);
        expect(onBench(wrapper)).toBe('stage/c.png');

        archive.value = {...archive.value, stage: archive.value.stage!.slice(0, 2)};
        wrapper.findComponent(StampedMount).vm.$emit('binned', '/stage-output/c.png');
        await vi.advanceTimersByTimeAsync(0);

        expect(onBench(wrapper)).toBe('stage/b.png');
        wrapper.unmount();
    });

    it('binning the last canister anywhere leaves the bench bare, not broken', async () => {
        apiMock.mockImplementation((path: string) => path === '/api/archive'
            ? Promise.resolve({stage: [{name: 'a.png', kind: 'image', mtime: Date.now() / 1000}], face: [], foley: []})
            : Promise.reject(new Error(`no window: ${path}`)));
        const wrapper = await openRoom();
        await wrapper.find('.canister').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        archive.value = {stage: [], face: [], foley: []};
        wrapper.findComponent(StampedMount).vm.$emit('binned', '/stage-output/a.png');
        await vi.advanceTimersByTimeAsync(0);

        expect(wrapper.find('.mount').exists()).toBe(false);
        expect(wrapper.find('.bench-bare').exists()).toBe(true);
        wrapper.unmount();
    });
});
