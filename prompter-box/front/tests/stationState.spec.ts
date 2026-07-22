import {describe, expect, it} from 'vitest';
import {stageLoad, stationReads, stationState, type StatusPayload} from '../src/lib/stationState';

// The callboard's state grammar as a tested contract — the exact mapping the
// single-file front carried in stationState()/poll() (#00063 §1B).

const darkStatus = (): StatusPayload => ({
    forge: {up: false, loaded: []},
    face_shop: {up: false} as StatusPayload['face_shop'],
    stage_job: {state: 'idle'},
    stage_ui: {up: false},
    foley: {installed: false},
});

describe('stationState', () => {
    it('everything dark on a cold floor', () => {
        expect(stationState(darkStatus())).toStrictEqual(
            {forge: 'dark', face: 'dark', stage: 'dark', foley: 'dark', kiln: 'dark'},
        );
    });

    it('forge: up with no voices loaded is ready; a loaded voice is standby with the roster read', () => {
        const s = darkStatus();
        s.forge = {up: true, loaded: []};
        expect(stationState(s).forge).toBe('ready');

        s.forge = {up: true, loaded: [{model: 'qwen3:14b', size_gb: 9.3}]};
        const st = stationState(s);
        expect(st.forge).toBe('standby');
        expect(stationReads(s, st).forge).toBe('qwen3:14b 9.3 GB');
    });

    it('stage: a running take is live; the full UI holding the GPU is held, never green', () => {
        const s = darkStatus();
        s.stage_job = {state: 'running', model: 'wan22-i2v-14b'};
        let st = stationState(s);
        expect(st.stage).toBe('live');
        expect(stationReads(s, st).stage).toBe('wan22-i2v-14b');

        s.stage_job = {state: 'idle'};
        s.stage_ui = {up: true};
        st = stationState(s);
        expect(st.stage).toBe('held');
        expect(stationReads(s, st).stage).toBe('the full UI holds :7860');
    });

    it('a live stage with no model name reads mid-take', () => {
        const s = darkStatus();
        s.stage_job = {state: 'running'};
        const st = stationState(s);
        expect(stationReads(s, st).stage).toBe('mid-take');
    });

    it('foley: not installed is dark; installed is ready; a running score is live and reads scoring', () => {
        const s = darkStatus();
        s.foley = {installed: true, job_state: 'idle'};
        expect(stationState(s).foley).toBe('ready');

        s.foley = {installed: true, job_state: 'running'};
        const st = stationState(s);
        expect(st.foley).toBe('live');
        expect(stationReads(s, st).foley).toBe('scoring');
    });

    it('kiln: rides the same state machine — live on a firing OR a night-shift row, held under the full UI, ready through a warm Face Shop', () => {
        const s = darkStatus();
        s.kiln = {job_state: 'running', subject: 'a black omafiets'};
        let st = stationState(s);
        expect(st.kiln).toBe('live');
        expect(stationReads(s, st).kiln).toBe('a black omafiets');

        const shift = darkStatus();
        shift.night_shift = {row_id: 'row-3', subject: 'terracotta geraniums'};
        st = stationState(shift);
        expect(st.kiln).toBe('live');
        expect(stationReads(shift, st).kiln).toBe('terracotta geraniums');

        const held = darkStatus();
        held.stage_ui = {up: true};
        st = stationState(held);
        expect(st.kiln).toBe('held');
        expect(stationReads(held, st).kiln).toBe('the full UI holds the GPU');

        const warm = darkStatus();
        warm.face_shop = {up: true} as StatusPayload['face_shop'];
        expect(stationState(warm).kiln).toBe('ready');
    });

    it('a live kiln with no subject anywhere reads firing', () => {
        const s = darkStatus();
        s.kiln = {job_state: 'running'};
        const st = stationState(s);
        expect(stationReads(s, st).kiln).toBe('firing');
    });

    it('face: a warm ComfyUI is standby', () => {
        const s = darkStatus();
        s.face_shop = {up: true} as StatusPayload['face_shop'];
        expect(stationState(s).face).toBe('standby');
    });
});

describe('stageLoad', () => {
    it('no invented numbers — a dark Face Shop carries no meter', () => {
        expect(stageLoad(darkStatus())).toStrictEqual({pct: 0, read: '— no meter · Face Shop dark'});
    });

    it('a warm Face Shop reports occupancy from the only VRAM truth the poll carries', () => {
        const s = darkStatus();
        s.face_shop = {up: true, vram_free_gb: 6, vram_total_gb: 24};
        const load = stageLoad(s);
        expect(load.pct).toBeCloseTo(75);
        expect(load.read).toBe('6 / 24 GB free');
    });

    it('the fill is clamped to the track', () => {
        const s = darkStatus();
        s.face_shop = {up: true, vram_free_gb: 30, vram_total_gb: 24};
        expect(stageLoad(s).pct).toBe(0);
    });
});
