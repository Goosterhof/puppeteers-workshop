import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import NightShiftRoom from '../src/rooms/NightShiftRoom.vue';

// The Night Shift's five wirings (#00063 Phase 4): add, remove, reorder,
// start, stop — plus the semicolon grammar and the running-shift lock.

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn<(path: string, body?: unknown) => Promise<unknown>>()}));
vi.mock('../src/composables/useBoothApi', () => ({api: apiMock}));

const routes = (overrides: Record<string, unknown> = {}) => (path: string): Promise<unknown> => {
    const table: Record<string, unknown> = {
        '/api/queue/list': {rows: [
            {id: 'r1', status: 'queued', subject: 'a terracotta pot', variant_count: 2, takes_done: 0},
        ], shift: {running: false}, log_tail: []},
        '/api/queue/add': {ok: true},
        '/api/queue/remove': {ok: true},
        '/api/queue/reorder': {ok: true},
        '/api/queue/start': {ok: true},
        '/api/queue/stop': {ok: true},
        ...overrides,
    };
    return path in table ? Promise.resolve(table[path]) : Promise.reject(new Error(`no window: ${path}`));
};

const boot = async () => {
    const wrapper = mount(NightShiftRoom, {props: {active: true}});
    await vi.advanceTimersByTimeAsync(0);
    return wrapper;
};

describe('NightShiftRoom', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        apiMock.mockReset();
        apiMock.mockImplementation(routes());
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('one phrase adds K seed-varied takes; semicolons add K distinct phrases', async () => {
        const wrapper = await boot();
        await wrapper.find('#shift-subject').setValue('a copper kettle');
        await wrapper.find('#shift-k').setValue('3');
        await wrapper.find('#shift-add').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(apiMock).toHaveBeenCalledWith('/api/queue/add', {
            subject: 'a copper kettle', variant_count: 3, job_type: 'kiln', two_sided: false,
        });

        await wrapper.find('#shift-subject').setValue('a kettle; a ladder; a gnome');
        await wrapper.find('#shift-add').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(apiMock).toHaveBeenCalledWith('/api/queue/add', {
            subject: ['a kettle', 'a ladder', 'a gnome'], variant_count: 3, job_type: 'kiln', two_sided: false,
        });
        expect(wrapper.find<HTMLInputElement>('#shift-subject').element.value).toBe('');
        wrapper.unmount();
    });

    it('an empty order is refused in the old voice', async () => {
        const wrapper = await boot();
        await wrapper.find('#shift-add').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(wrapper.find('.error').text()).toBe('An order needs a subject — the kiln fires nothing from an empty phrase.');
        wrapper.unmount();
    });

    it('reorder and remove ride the row id; start and stop flip the shift', async () => {
        const wrapper = await boot();
        const handles = wrapper.findAll('.order .handles .act');
        await handles[0]!.trigger('click');
        await handles[1]!.trigger('click');
        await handles[2]!.trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(apiMock).toHaveBeenCalledWith('/api/queue/reorder', {row_id: 'r1', direction: 'up'});
        expect(apiMock).toHaveBeenCalledWith('/api/queue/reorder', {row_id: 'r1', direction: 'down'});
        expect(apiMock).toHaveBeenCalledWith('/api/queue/remove', {row_id: 'r1'});

        await wrapper.find('#shift-start').trigger('click');
        await wrapper.find('#shift-stop').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(apiMock).toHaveBeenCalledWith('/api/queue/start', {});
        expect(apiMock).toHaveBeenCalledWith('/api/queue/stop', {});
        wrapper.unmount();
    });

    it('a running shift holds the start button on the floor', async () => {
        apiMock.mockImplementation(routes({'/api/queue/list': {
            rows: [{id: 'r1', status: 'firing', subject: 'a pot', variant_count: 2, takes_done: 1}],
            shift: {running: true}, log_tail: ['firing r1'],
        }}));
        const wrapper = await boot();
        const start = wrapper.find<HTMLButtonElement>('#shift-start');
        expect(start.text()).toBe('The shift is on the floor');
        expect(start.element.disabled).toBe(true);
        expect(wrapper.find('.order').attributes('data-status')).toBe('firing');
        expect(wrapper.find('.order .progress').text()).toBe('take 2/2');
        wrapper.unmount();
    });
});
