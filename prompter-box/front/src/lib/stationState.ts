// The callboard's state grammar, extracted pure from the single-file front so
// the mapping is a tested contract instead of folklore (#00063 §1B).
// Input is the /api/status payload; output is one of the five lamp states per
// station: dark | ready | standby | held | live.

export interface LoadedModel {
    model: string;
    size_gb: number;
}

// The /api/status payload — the callboard's whole vocabulary, typed once.
export interface StatusPayload {
    forge: {up: boolean; loaded: LoadedModel[]};
    face_shop: {up: boolean; vram_free_gb: number; vram_total_gb: number; painting?: boolean};
    // driver truth via nvidia-smi — answers even when the Face Shop is dark
    gpu?: {vram_free_gb: number; vram_total_gb: number} | null;
    stage_job: {state: string; model?: string};
    stage_ui: {up: boolean};
    foley: {installed: boolean; job_state?: string};
    kiln?: {job_state?: string; subject?: string};
    night_shift?: {row_id?: number | string; subject?: string};
}

export type LampState = 'dark' | 'ready' | 'standby' | 'held' | 'live';
export type StationName = 'forge' | 'face' | 'stage' | 'foley' | 'kiln';
export type StationStates = Record<StationName, LampState>;
export type StationReads = Record<StationName, string>;

export interface StageLoad {
    pct: number;
    read: string;
}

export function stationState(s: StatusPayload): StationStates {
    return {
        forge: !s.forge.up ? 'dark' : s.forge.loaded.length ? 'standby' : 'ready',
        // a running paint — booth-cued or full-UI — is a performance (#00085)
        face: !s.face_shop.up ? 'dark' : s.face_shop.painting ? 'live' : 'standby',
        stage: s.stage_job.state === 'running' ? 'live'
            : s.stage_ui.up ? 'held' : 'dark', // held, not green — a held stage refuses every cue
        foley: !s.foley.installed ? 'dark'
            : s.foley.job_state === 'running' ? 'live' : 'ready',
        // the fifth plate rides the SAME state machine — no second dialect
        kiln: (s.kiln?.job_state === 'running' || s.night_shift?.row_id) ? 'live'
            : s.stage_ui.up ? 'held' // the full UI occupies the GPU
            : s.face_shop.up ? 'ready' : 'dark', // the kiln fires through ComfyUI
    };
}

export function stationReads(s: StatusPayload, st: StationStates): StationReads {
    return {
        forge: st.forge === 'standby'
            ? s.forge.loaded.map(m => `${m.model} ${m.size_gb} GB`).join(' · ') : '',
        face: st.face === 'live' ? 'mid-paint' : '',
        stage: st.stage === 'live' ? (s.stage_job.model || 'mid-take')
            : st.stage === 'held' ? 'the full UI holds :7860' : '',
        foley: st.foley === 'live' ? 'scoring' : '',
        kiln: st.kiln === 'live' ? (s.night_shift?.subject || s.kiln?.subject || 'firing')
            : st.kiln === 'held' ? 'the full UI holds the GPU' : '',
    };
}

// The dimmer: the Face Shop's self-report first; when it is dark, the driver
// (nvidia-smi, the guard's own instrument) so the meter never reads "no
// meter" while the GPU is alive (#00085 detonation 2). No invented numbers —
// the meter only goes dark when the driver itself is silent.
const meter = (free: number, total: number, source = ''): StageLoad => ({
    pct: Math.max(0, Math.min(100, (1 - free / total) * 100)),
    read: `${free} / ${total} GB free${source}`,
});

export function stageLoad(s: StatusPayload): StageLoad {
    if (s.face_shop.up) return meter(s.face_shop.vram_free_gb, s.face_shop.vram_total_gb);
    if (s.gpu) return meter(s.gpu.vram_free_gb, s.gpu.vram_total_gb, ' · driver');
    return {pct: 0, read: '— no meter · the driver is silent'};
}
