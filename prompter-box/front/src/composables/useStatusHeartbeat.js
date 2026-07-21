import {onMounted, onUnmounted, reactive} from 'vue';
import {stageLoad, stationReads, stationState} from '../lib/stationState.js';
import {api} from './useBoothApi.js';

const STATIONS = ['forge', 'face', 'stage', 'foley', 'kiln'];

async function evict() {
    const {evicted} = await api('/api/evict', {});
    return evicted;
}

// The callboard heartbeat — the /api/status poll behind the five lamps and
// the dimmer (#00063 §1B). A failed poll goes cold immediately: every lamp
// dark, no invented numbers. The take-running amber wash is a body class so
// the mutex is felt page-wide, same as the single-file front.
export function useStatusHeartbeat({intervalMs = 5000} = {}) {
    const board = reactive({
        cold: false,
        takeRunning: false,
        stations: Object.fromEntries(STATIONS.map(n => [n, {state: 'dark', read: ''}])),
        occ: {pct: 0, read: '—'},
    });

    async function poll() {
        try {
            const s = await api('/api/status');
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

    let timer = null;
    onMounted(() => {
        poll();
        timer = setInterval(poll, intervalMs);
    });
    onUnmounted(() => clearInterval(timer));

    return {board, poll, evict};
}
