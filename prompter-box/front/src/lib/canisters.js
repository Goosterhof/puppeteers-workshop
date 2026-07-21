// The Canisters' pure grammar — ages, rooms, chips, and the shelf filter —
// extracted 1:1 from the single-file front (#00063 Phase 2).

export const ROOMS = {
    stage: {label: 'Stage', src: '/stage-output/'},
    face: {label: 'Face Shop', src: '/face-output/'},
    foley: {label: 'Foley', src: '/foley-output/'},
};

export const age = ts => {
    const s = Date.now() / 1000 - ts;
    return s < 90 ? 'just now' : s < 5400 ? `${Math.round(s / 60)} min ago`
        : s < 172800 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`;
};

export function canisterChips(it, {fresh = false} = {}) {
    const m = it.meta || {};
    const chips = [[ROOMS[it.room].label, 'chip room']];
    if (m.model) chips.push([m.model, 'chip']);
    if (m.seed !== undefined) chips.push([`seed ${m.seed}`, 'chip']);
    if (m.steps) chips.push([`${m.steps} steps`, 'chip']);
    if (m.guidance !== undefined) chips.push([`cfg ${m.guidance}`, 'chip']);
    if (m.resolution) chips.push([m.resolution, 'chip']);
    if (m.frames) chips.push([`${m.frames} fr`, 'chip']);
    if (m.duration_s) chips.push([`${m.duration_s}s`, 'chip']);
    for (const l of m.loras || []) chips.push([`+ ${l}`, 'chip']);
    if (!fresh) {
        // a fresh take wears the Fresh stamp instead of an age chip — same DNA, different moment
        chips.push([age(it.mtime), 'chip']);
        if (it.size) chips.push([`${(it.size / 1048576).toFixed(1)} MB`, 'chip']);
    }
    return chips;
}

// The shelf filter — room pill, kind pill, and the free-text search over
// filename + meta, newest first (the old archItems()).
export function filterArchive(archive, {room = '', kind = '', search = ''} = {}) {
    const q = search.trim().toLowerCase();
    return Object.keys(ROOMS)
        .filter(r => !room || r === room)
        .flatMap(r => (archive[r] || []).map(it => ({...it, room: r})))
        .filter(it => (!kind || it.kind === kind)
            && (!q || `${it.name} ${JSON.stringify(it.meta || {})}`.toLowerCase().includes(q)))
        .sort((a, b) => b.mtime - a.mtime);
}
