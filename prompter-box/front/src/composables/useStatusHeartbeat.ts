import {onMounted, onUnmounted, reactive} from 'vue';
import type {LampState, StageLoad, StationName, StatusPayload} from '../lib/stationState';
import {stageLoad, stationReads, stationState} from '../lib/stationState';
import {api} from './useBoothApi';

const STATIONS: StationName[] = ['forge', 'face', 'stage', 'foley', 'kiln'];

export interface CallboardState {
    cold: boolean;
    takeRunning: boolean;
    stations: Record<StationName, {state: LampState; read: string}>;
    occ: StageLoad;
}

async function evict(): Promise<string[]> {
    const {evicted} = await api<{evicted: string[]}>('/api/evict', {});
    return evicted;
}

// The callboard heartbeat — the /api/status poll behind the five lamps and
// the dimmer (#00063 §1B). A failed poll goes cold immediately: every lamp
// dark, no invented numbers. `take-running` is a body class because the VRAM
// mutex is a global fact, not a room's — but the heat it drives hangs on the
// active dog-ear (App.vue), never on <body>: the folio deck, the rail and the
// pit tile 100% of #app opaquely, so a body wash reaches no eye (#00109 D1).
export function useStatusHeartbeat({intervalMs = 5000}: {intervalMs?: number} = {}) {
    const board = reactive<CallboardState>({
        cold: false,
        takeRunning: false,
        stations: Object.fromEntries(
            STATIONS.map(n => [n, {state: 'dark', read: ''}]),
        ) as CallboardState['stations'],
        occ: {pct: 0, read: '—'},
    });

    async function poll() {
        try {
            const s = await api<StatusPayload>('/api/status');
            board.cold = false;
            const st = stationState(s);
            const reads = stationReads(s, st);
            for (const n of STATIONS) {
                board.stations[n].state = st[n];
                board.stations[n].read = reads[n];
            }
            board.takeRunning = Object.values(st).includes('live');
            board.occ = stageLoad(s);
        } catch {
            board.cold = true;
            board.takeRunning = false;
            for (const n of STATIONS) {
                board.stations[n].state = 'dark';
                board.stations[n].read = '';
            }
            board.occ = {pct: 0, read: '—'};
        }
        document.body.classList.toggle('take-running', board.takeRunning);
    }

    let timer: ReturnType<typeof setInterval> | null = null;
    onMounted(() => {
        poll();
        timer = setInterval(poll, intervalMs);
    });
    onUnmounted(() => {
        if (timer !== null) clearInterval(timer);
    });

    return {board, poll, evict};
}
