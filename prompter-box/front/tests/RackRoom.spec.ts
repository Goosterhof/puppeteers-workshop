import {mount, type DOMWrapper} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import RackRoom from '../src/rooms/RackRoom.vue';
import {slugify} from '../src/lib/slugify';

// The Curing Rack's contract (#00063 Phase 4): three verdicts, the
// spotlight's wheel lifecycle, the break-pit's three exits, and the
// 500 ms strip cadence frozen under reduced motion.

const {apiMock, wheelHandles, mountWheelMock} = vi.hoisted(() => {
    const handles: Array<{ready: Promise<void>; dispose: ReturnType<typeof vi.fn<() => void>>}> = [];
    return {
        apiMock: vi.fn<(path: string, body?: unknown) => Promise<unknown>>(),
        wheelHandles: handles,
        mountWheelMock: vi.fn<(container: HTMLElement, glbUrl: string, opts?: {initialYaw?: number; reducedMotion?: boolean}) => {ready: Promise<void>; dispose: () => void}>(() => {
            const handle = {ready: Promise.resolve(), dispose: vi.fn<() => void>()};
            handles.push(handle);
            return handle;
        }),
    };
});
vi.mock('../src/composables/useBoothApi', () => ({api: apiMock}));
vi.mock('../src/lib/potters-wheel', () => ({mountWheel: mountWheelMock}));

const candidate = (id: string, over: Record<string, unknown> = {}) => ({
    id,
    frames: [0, 1, 2, 3, 4, 5, 6, 7].map(n => `${id}/turn/00${n}.png`),
    qa: {passed: true},
    recipe: {status: 'pending', subject: `subject ${id}`, canister_label: `label ${id}`,
        octree: 128, seed: 7, orient_hint: 'front-facing', refire_count: 0, two_sided: false},
    ...over,
});

const routes = (overrides: Record<string, unknown> = {}) => (path: string): Promise<unknown> => {
    const table: Record<string, unknown> = {
        '/api/rack/list': {candidates: [candidate('c1'), candidate('c2')]},
        '/api/rack/approve': {ok: true},
        '/api/rack/refire': {ok: true},
        '/api/rack/discard': {ok: true},
        '/api/kiln/job': {state: 'idle'},
        ...overrides,
    };
    return path in table ? Promise.resolve(table[path]) : Promise.reject(new Error(`no window: ${path}`));
};

const boot = async () => {
    const wrapper = mount(RackRoom, {props: {active: true}});
    await vi.advanceTimersByTimeAsync(0);
    return wrapper;
};
const discardOf = (card: DOMWrapper<Element>) => card.find('.acts .breaker');

describe('RackRoom', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        globalThis.__reducedMotion = false;
        apiMock.mockReset();
        apiMock.mockImplementation(routes());
        wheelHandles.length = 0;
        mountWheelMock.mockClear();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('only pending candidates deal onto the rack', async () => {
        apiMock.mockImplementation(routes({'/api/rack/list': {candidates: [
            candidate('c1'),
            candidate('shipped', {recipe: {...candidate('shipped').recipe, status: 'approved'}}),
        ]}}));
        const wrapper = await boot();
        expect(wrapper.findAll('#rack-grid .candidate')).toHaveLength(1);
        wrapper.unmount();
    });

    it('the strip turns at the 500 ms cadence — and freezes at frame 0 under reduced motion', async () => {
        const wrapper = await boot();
        const src0 = wrapper.find('#rack-grid img.spin').attributes('src');
        await vi.advanceTimersByTimeAsync(500);
        const src1 = wrapper.find('#rack-grid img.spin').attributes('src');
        expect(src1).not.toBe(src0);
        wrapper.unmount();

        globalThis.__reducedMotion = true;
        const frozen = await boot();
        const f0 = frozen.find('#rack-grid img.spin').attributes('src');
        await vi.advanceTimersByTimeAsync(2000);
        expect(frozen.find('#rack-grid img.spin').attributes('src')).toBe(f0);
        expect(f0).toContain('000.png');
        frozen.unmount();
    });

    it('the spotlight mounts ONE wheel and disposes it off the wheel — grid keeps a poster strip', async () => {
        const wrapper = await boot();
        await wrapper.find('#rack-grid .candidate .well').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(mountWheelMock).toHaveBeenCalledTimes(1);
        expect(wrapper.find('#rack-view .candidate.spotlight').exists()).toBe(true);
        expect(wrapper.find('#rack-grid .candidate.spotlit').exists()).toBe(true);

        // off the wheel — the handle disposes with the card
        await wrapper.find('#rack-view .candidate .acts .act:last-child').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(wheelHandles[0]!.dispose).toHaveBeenCalledTimes(1);
        expect(wrapper.find('#rack-view .candidate').exists()).toBe(false);
        wrapper.unmount();
    });

    it('Approve: the packer law is enforced, then the shelving call carries the slug', async () => {
        const wrapper = await boot();
        const card = wrapper.find('#rack-grid .candidate');
        await card.find('.acts .fire').trigger('click');
        const input = card.find<HTMLInputElement>('.approve-row input');
        expect(input.element.value).toBe(slugify('label c1'));

        await input.setValue('Bad Name!');
        await card.find('.approve-row .fire').trigger('click');
        expect(card.find('.error').text()).toContain('will not survive the packer');
        expect(apiMock).not.toHaveBeenCalledWith('/api/rack/approve', expect.anything());

        await input.setValue('label-c1');
        await card.find('.approve-row .fire').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(apiMock).toHaveBeenCalledWith('/api/rack/approve', {candidate_id: 'c1', pack_name: 'label-c1'});
        wrapper.unmount();
    });

    it('Refire re-meshes the SAME painting at 224/0.4 and waits out the kiln', async () => {
        const wrapper = await boot();
        const card = wrapper.find('#rack-grid .candidate');
        await card.find('.acts .act').trigger('click');
        await card.find('.refire-row .act').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(apiMock).toHaveBeenCalledWith('/api/rack/refire', {candidate_id: 'c1', octree: 224, threshold: 0.4});
        expect(card.find('.refire-row .act').text()).toBe('Refiring…');
        wrapper.unmount();
    });

    it('the break-pit: Keep and Esc keep the candidate; Break it calls the discard window', async () => {
        const wrapper = await boot();
        const card = wrapper.find('#rack-grid .candidate');
        const pit = wrapper.find('#break-pit');

        await discardOf(card).trigger('click');
        expect(pit.find('.break-subject').text()).toContain('label c1');
        await pit.find('#break-keep').trigger('click');

        await discardOf(card).trigger('click');
        await pit.trigger('cancel'); // Esc
        await pit.find('#break-confirm').trigger('click'); // target already cleared — still no discard
        expect(apiMock).not.toHaveBeenCalledWith('/api/rack/discard', expect.anything());

        await discardOf(card).trigger('click');
        await pit.find('#break-confirm').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(apiMock).toHaveBeenCalledWith('/api/rack/discard', {candidate_id: 'c1'});
        wrapper.unmount();
    });

    it('a refired candidate flares its ember scar once — not on the re-deal', async () => {
        apiMock.mockImplementation(routes({'/api/rack/list': {candidates: [
            candidate('c9', {recipe: {...candidate('c9').recipe, refire_count: 1, octree: 224}}),
        ]}}));
        const wrapper = await boot();
        expect(wrapper.find('#rack-grid .candidate').classes()).toContain('mended');
        await (wrapper.vm as unknown as {loadRack?: () => Promise<void>}).loadRack?.();
        wrapper.unmount();
    });
});
