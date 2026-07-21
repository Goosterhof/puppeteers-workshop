// The callboard's state grammar, extracted pure from the single-file front so
// the mapping is a tested contract instead of folklore (#00063 §1B).
// Input is the /api/status payload; output is one of the five lamp states per
// station: dark | ready | standby | held | live.

export function stationState(s) {
    return {
        forge: !s.forge.up ? 'dark' : s.forge.loaded.length ? 'standby' : 'ready',
        face: s.face_shop.up ? 'standby' : 'dark',
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

export function stationReads(s, st) {
    return {
        forge: st.forge === 'standby'
            ? s.forge.loaded.map(m => `${m.model} ${m.size_gb} GB`).join(' · ') : '',
        face: '',
        stage: st.stage === 'live' ? (s.stage_job.model || 'mid-take')
            : st.stage === 'held' ? 'the full UI holds :7860' : '',
        foley: st.foley === 'live' ? 'scoring' : '',
        kiln: st.kiln === 'live' ? (s.night_shift?.subject || s.kiln?.subject || 'firing')
            : st.kiln === 'held' ? 'the full UI holds the GPU' : '',
    };
}

// The dimmer: the only VRAM truth the poll carries is the Face Shop's —
// no invented numbers when it is dark.
export function stageLoad(s) {
    if (!s.face_shop.up) return {pct: 0, read: '— no meter · Face Shop dark'};
    const {vram_free_gb: free, vram_total_gb: total} = s.face_shop;
    return {
        pct: Math.max(0, Math.min(100, (1 - free / total) * 100)),
        read: `${free} / ${total} GB free`,
    };
}
