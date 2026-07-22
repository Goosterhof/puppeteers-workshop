// The job poller — the 3-miss tolerance contract, written once (#00063 §1A).
//
// Every room that watches a long job (Stage, Kiln, Foley) polls the same way:
// a fetch failure under the tolerance is silent (the next tick retries); the
// third consecutive miss kills the poller and voices the loss exactly once.
// A successful fetch resets the miss count. A job that leaves the 'running'
// state settles the poller.
//
// createJobPoller is deliberately framework-free so the contract is unit-
// testable with fake timers; rooms wire it up inside their own lifecycle.

export interface JobPollerOptions<J extends {state?: string}> {
    fetchJob: () => Promise<J>;
    intervalMs?: number;
    missTolerance?: number;
    onTick?: (job: J) => void;
    onSettled?: (job: J) => void;
    onLost?: (err: unknown) => void;
}

export interface JobPoller {
    start: () => void;
    stop: () => void;
    readonly running: boolean;
}

export function createJobPoller<J extends {state?: string}>(
    {fetchJob, intervalMs = 3000, missTolerance = 3, onTick, onSettled, onLost}: JobPollerOptions<J>,
): JobPoller {
    let timer: ReturnType<typeof setInterval> | null = null;
    let misses = 0;

    const stop = () => {
        if (timer !== null) clearInterval(timer);
        timer = null;
    };

    const beat = async () => {
        let job: J;
        try {
            job = await fetchJob();
            misses = 0;
        } catch (err) {
            misses += 1;
            if (misses < missTolerance) return;
            stop();
            onLost?.(err);
            return;
        }
        onTick?.(job);
        if (job.state === 'running') return;
        stop();
        onSettled?.(job);
    };

    const start = () => {
        stop();
        misses = 0;
        timer = setInterval(beat, intervalMs);
    };

    return {
        start,
        stop,
        get running() {
            return timer !== null;
        },
    };
}
