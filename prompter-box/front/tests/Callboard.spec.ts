import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import Callboard from '../src/components/Callboard.vue';
import type {StatusPayload} from '../src/lib/stationState';

// The footlight ledger (#00064 Phase C): five stations typed along the stage
// lip, LIVE signalled by value and never by pulse, and a blackout that darkens
// the SHOWN state while the heartbeat's truth returns with the relight poll.

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn<(path: string, body?: unknown) => Promise<unknown>>()}));
vi.mock('../src/composables/useBoothApi', () => ({api: apiMock}));

const status = (over: Partial<StatusPayload> = {}): StatusPayload => ({
    forge: {up: true, loaded: []},
    face_shop: {up: false, vram_free_gb: 0, vram_total_gb: 24},
    stage_job: {state: 'idle'},
    stage_ui: {up: false},
    foley: {installed: true},
    ...over,
});

const routes = (payload: StatusPayload, evicted: string[] = []) => (path: string): Promise<unknown> =>
    path === '/api/status' ? Promise.resolve(payload)
        : path === '/api/evict' ? Promise.resolve({evicted})
            : Promise.reject(new Error(`no window: ${path}`));

const raise = async (payload = status(), evicted: string[] = []) => {
    apiMock.mockImplementation(routes(payload, evicted));
    const w = mount(Callboard);
    await vi.advanceTimersByTimeAsync(0);
    return w;
};
const item = (w: Awaited<ReturnType<typeof raise>>, id: string) => w.get(`[data-station="${id}"]`);
const word = (w: Awaited<ReturnType<typeof raise>>, id: string) => item(w, id).get('.st').text();

describe('Callboard — the footlight ledger', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        apiMock.mockReset();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('the five stations read L→R in wiring order, each carrying its machine as its cue', async () => {
        const w = await raise();
        expect(w.findAll('.ledger-item').map(i => i.attributes('data-station')))
            .toStrictEqual(['forge', 'face', 'stage', 'foley', 'kiln']);
        expect(item(w, 'kiln').attributes('title')).toBe('Hunyuan3D · Klein');
        w.unmount();
    });

    it('the Face Shop reads "warm" on standby, and a live station shouts', async () => {
        const w = await raise(status({
            face_shop: {up: true, vram_free_gb: 6, vram_total_gb: 24},
            stage_job: {state: 'running', model: 'i2v 14B'},
        }));
        expect(word(w, 'face')).toBe('warm'); // resident, not idle-cold
        expect(word(w, 'stage')).toBe('LIVE');
        expect(item(w, 'stage').classes()).toContain('is-live');
        w.unmount();
    });

    it('only the stations holding something get a margin note', async () => {
        const w = await raise(status({
            face_shop: {up: true, vram_free_gb: 6, vram_total_gb: 24},
            stage_ui: {up: true},
        }));
        expect(item(w, 'stage').get('.rd').text()).toContain('the full UI holds :7860');
        expect(item(w, 'face').find('.rd').exists()).toBe(false); // warm speaks for itself
        expect(w.get('#occ-read').text()).toContain('Stage load 75%');
        w.unmount();
    });

    it('a failed poll goes cold — every lamp dark, and no invented numbers', async () => {
        apiMock.mockRejectedValue(new Error('the booth is not answering'));
        const w = mount(Callboard);
        await vi.advanceTimersByTimeAsync(0);
        expect(w.get('#callboard').classes()).toContain('cold');
        expect(w.findAll('.ledger-item').every(i => i.classes().includes('is-dark'))).toBe(true);
        expect(w.get('#occ-read').text()).toBe('Stage load 0% · —');
        w.unmount();
    });

    it('the heartbeat keeps time, and a live take washes the whole booth amber', async () => {
        const w = await raise(status({stage_job: {state: 'running'}}));
        expect(document.body.classList.contains('take-running')).toBe(true);

        apiMock.mockImplementation(routes(status()));
        await vi.advanceTimersByTimeAsync(5000); // the next beat
        expect(word(w, 'stage')).toBe('dark');
        expect(document.body.classList.contains('take-running')).toBe(false);
        w.unmount();
    });

    it('clearing the boards: every lamp cools by value, then the relight poll restores the truth', async () => {
        const w = await raise(status({face_shop: {up: true, vram_free_gb: 6, vram_total_gb: 24}}), ['qwen3:14b']);
        expect(word(w, 'face')).toBe('warm');

        await w.get('#evict').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(w.get('#callboard').classes()).toContain('blackout');
        expect(w.findAll('.ledger-item').every(i => i.classes().includes('is-dark'))).toBe(true);
        expect(w.get('#evict').text()).toBe('1 voice left the boards');

        await vi.advanceTimersByTimeAsync(1200); // the relight
        expect(w.get('#callboard').classes()).not.toContain('blackout');
        expect(word(w, 'face')).toBe('warm');

        await vi.advanceTimersByTimeAsync(1400); // the label settles back
        expect(w.get('#evict').text()).toBe('clear the boards');
        w.unmount();
    });

    it('an empty sweep and a dead booth each say so in the booth\'s own voice', async () => {
        const empty = await raise(status(), []);
        await empty.get('#evict').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(empty.get('#evict').text()).toBe('the boards were already clear');
        empty.unmount();

        const w = await raise(status());
        apiMock.mockImplementation((path: string) => path === '/api/evict'
            ? Promise.reject(new Error('down'))
            : Promise.resolve(status()));
        await w.get('#evict').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(w.get('#evict').text()).toBe('the booth is not answering');
        w.unmount();
    });
});
