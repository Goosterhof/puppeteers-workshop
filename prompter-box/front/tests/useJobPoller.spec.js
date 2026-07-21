import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createJobPoller} from '../src/composables/useJobPoller.js';

// The 3-miss tolerance contract (#00063 §1A acceptance):
//   miss < 3  → silent, the next tick retries
//   miss = 3  → the poller dies and voices the loss exactly once
// plus: a successful fetch resets the count, and a settled job stops the beat.

const INTERVAL = 3000;

describe('createJobPoller', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    const tick = async (n = 1) => {
        for (let i = 0; i < n; i += 1) {
            await vi.advanceTimersByTimeAsync(INTERVAL);
        }
    };

    it('stays silent under the tolerance — two misses voice nothing and the beat goes on', async () => {
        const fetchJob = vi.fn()
            .mockRejectedValueOnce(new Error('gone'))
            .mockRejectedValueOnce(new Error('gone'))
            .mockResolvedValue({state: 'running'});
        const onLost = vi.fn();
        const poller = createJobPoller({fetchJob, intervalMs: INTERVAL, onLost});
        poller.start();

        await tick(2);
        expect(onLost).not.toHaveBeenCalled();
        expect(poller.running).toBe(true);

        await tick();
        expect(fetchJob).toHaveBeenCalledTimes(3);
        expect(onLost).not.toHaveBeenCalled();
    });

    it('dies loudly on the third consecutive miss — onLost once, no further polling', async () => {
        const fetchJob = vi.fn().mockRejectedValue(new Error('the server stopped answering'));
        const onLost = vi.fn();
        const onSettled = vi.fn();
        const poller = createJobPoller({fetchJob, intervalMs: INTERVAL, onLost, onSettled});
        poller.start();

        await tick(3);
        expect(onLost).toHaveBeenCalledTimes(1);
        expect(poller.running).toBe(false);

        await tick(3);
        expect(fetchJob).toHaveBeenCalledTimes(3);
        expect(onLost).toHaveBeenCalledTimes(1);
        expect(onSettled).not.toHaveBeenCalled();
    });

    it('a successful fetch resets the miss count', async () => {
        const fetchJob = vi.fn()
            .mockRejectedValueOnce(new Error('gone'))
            .mockRejectedValueOnce(new Error('gone'))
            .mockResolvedValueOnce({state: 'running'})
            .mockRejectedValueOnce(new Error('gone'))
            .mockRejectedValueOnce(new Error('gone'))
            .mockResolvedValue({state: 'running'});
        const onLost = vi.fn();
        const poller = createJobPoller({fetchJob, intervalMs: INTERVAL, onLost});
        poller.start();

        await tick(6);
        expect(onLost).not.toHaveBeenCalled();
        expect(poller.running).toBe(true);
    });

    it('keeps ticking while the job runs, settles once it leaves the running state', async () => {
        const fetchJob = vi.fn()
            .mockResolvedValueOnce({state: 'running', log_tail: ['a']})
            .mockResolvedValueOnce({state: 'running', log_tail: ['a', 'b']})
            .mockResolvedValue({state: 'done', outputs: ['take.webm']});
        const onTick = vi.fn();
        const onSettled = vi.fn();
        const poller = createJobPoller({fetchJob, intervalMs: INTERVAL, onTick, onSettled});
        poller.start();

        await tick(2);
        expect(onTick).toHaveBeenCalledTimes(2);
        expect(onSettled).not.toHaveBeenCalled();

        await tick();
        expect(onSettled).toHaveBeenCalledWith({state: 'done', outputs: ['take.webm']});
        expect(poller.running).toBe(false);

        await tick(2);
        expect(fetchJob).toHaveBeenCalledTimes(3);
        expect(onSettled).toHaveBeenCalledTimes(1);
    });

    it('start() twice never doubles the beat', async () => {
        const fetchJob = vi.fn().mockResolvedValue({state: 'running'});
        const poller = createJobPoller({fetchJob, intervalMs: INTERVAL});
        poller.start();
        poller.start();

        await tick();
        expect(fetchJob).toHaveBeenCalledTimes(1);
        poller.stop();
    });
});
