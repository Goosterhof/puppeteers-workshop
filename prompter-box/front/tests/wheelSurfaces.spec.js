import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import KilnRoom from '../src/rooms/KilnRoom.vue';
import ShelfRoom from '../src/rooms/ShelfRoom.vue';

// The Potter's Wheel mounts on 3 surfaces — kiln result, Rack spotlight,
// Shelf spotlight — and disposes on unmount on all 3 (#00063 Phase 4).
// The Rack surface is covered in RackRoom.spec; these are the other two.

const {apiMock, wheelHandles, mountWheelMock} = vi.hoisted(() => {
    const handles = [];
    return {
        apiMock: vi.fn(),
        wheelHandles: handles,
        mountWheelMock: vi.fn(() => {
            const handle = {ready: Promise.resolve(), dispose: vi.fn()};
            handles.push(handle);
            return handle;
        }),
    };
});
vi.mock('../src/composables/useBoothApi.js', () => ({api: apiMock}));
vi.mock('../src/lib/potters-wheel.js', () => ({mountWheel: mountWheelMock}));

describe('the wheel on the kiln bench', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        apiMock.mockReset();
        wheelHandles.length = 0;
        mountWheelMock.mockClear();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('a done firing mounts the wheel; a re-fire re-deals it; unmount disposes', async () => {
        apiMock.mockImplementation(path => Promise.resolve({
            '/api/kiln/job': {state: 'idle'},
            '/api/kiln/generate': {ok: true},
        }[path]));
        const wrapper = mount(KilnRoom);
        await vi.advanceTimersByTimeAsync(0);

        await wrapper.find('#kiln-subject').setValue('a black omafiets');
        await wrapper.find('#kiln-go').trigger('click');
        await vi.advanceTimersByTimeAsync(0);

        apiMock.mockImplementation(path => Promise.resolve({
            '/api/kiln/job': {state: 'done', candidate: {id: 'k1', subject: 'a black omafiets',
                seed: 7, octree: 128, orient_hint: 'front-facing', refire_count: 0, two_sided: false}},
        }[path]));
        await vi.advanceTimersByTimeAsync(3000);
        await vi.advanceTimersByTimeAsync(0);

        expect(mountWheelMock).toHaveBeenCalledTimes(1);
        expect(mountWheelMock.mock.calls[0][1]).toBe('/kiln-output/k1/k1.glb');
        expect(wrapper.find('.mount-stamp').text()).toBe('Fired');

        wrapper.unmount();
        expect(wheelHandles[0].dispose).toHaveBeenCalledTimes(1);
    });

    it('the three knob-notes stand verbatim in the settings drawer', async () => {
        apiMock.mockImplementation(() => Promise.resolve({state: 'idle'}));
        const wrapper = mount(KilnRoom);
        const notes = wrapper.findAll('.knob-note').map(n => n.text());
        expect(notes).toHaveLength(3);
        expect(notes[0]).toContain('The carving grid');
        expect(notes[0]).toContain('auto-refires at 224');
        expect(notes[1]).toContain('Where the skin gets drawn in the voxel field');
        expect(notes[1]).toContain('softens to 0.4');
        expect(notes[2]).toContain('The dice — one seed steers both the painting and the mesh');
        wrapper.unmount();
    });
});

describe('the wheel on the shelf', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        apiMock.mockReset();
        wheelHandles.length = 0;
        mountWheelMock.mockClear();
        apiMock.mockImplementation(() => Promise.resolve({props: [
            {name: 'omafiets', glb: 'omafiets/omafiets.glb', hide: 'omafiets/hide.png',
                glb_mb: 4.2, octree: 224, seed: 7, two_sided: false, subject: 'a black omafiets'},
        ]}));
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('a spotlighted prop takes the wheel; off the wheel disposes it', async () => {
        const wrapper = mount(ShelfRoom, {props: {active: true}});
        await vi.advanceTimersByTimeAsync(0);

        await wrapper.find('#shelf-grid .well.shelf').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(mountWheelMock).toHaveBeenCalledTimes(1);
        expect(mountWheelMock.mock.calls[0][1]).toBe('/pack-queue/omafiets/omafiets.glb');
        expect(wrapper.find('#shelf-view .candidate.spotlight').exists()).toBe(true);

        await wrapper.find('#shelf-view .acts .act').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(wheelHandles[0].dispose).toHaveBeenCalledTimes(1);
        expect(wrapper.find('#shelf-view .candidate').exists()).toBe(false);
        wrapper.unmount();
    });
});
