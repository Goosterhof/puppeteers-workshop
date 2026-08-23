import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import StampedMount from '../src/components/StampedMount.vue';

// Take it home (2026-08-23): every mount carries a Download act, images also
// a Copy act, and the rooms' own acts still follow.

describe('StampedMount', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.stubGlobal('ClipboardItem', class {
            constructor(public parts: Record<string, Blob>) {}
        });
    });
    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    const paint = (extra = {}) => mount(StampedMount, {props: {
        room: 'face', url: '/face-output/PrompterBox-001020_00001_.png', kind: 'image', title: 'a night watchman', ...extra,
    }});

    it('offers the take as a same-origin download named after the file', () => {
        const w = paint();
        const a = w.find('a.take-home');
        expect(a.attributes('href')).toBe('/face-output/PrompterBox-001020_00001_.png');
        expect(a.attributes('download')).toBe('PrompterBox-001020_00001_.png');
        w.unmount();
    });

    it('offers Copy image only when the browser will take one, and only for images', () => {
        vi.stubGlobal('navigator', {clipboard: {write: vi.fn<() => Promise<void>>()}});
        const img = paint();
        expect(img.findAll('button.take-home')).toHaveLength(1);
        img.unmount();
        const vid = paint({kind: 'video', url: '/stage-output/take.mp4'});
        expect(vid.findAll('button.take-home')).toHaveLength(0);
        expect(vid.find('a.take-home').attributes('download')).toBe('take.mp4');
        vid.unmount();
        vi.stubGlobal('navigator', {});
        const shut = paint();
        expect(shut.findAll('button.take-home')).toHaveLength(0);
        expect(shut.find('a.take-home').exists()).toBe(true);
        shut.unmount();
    });

    it('copies the take and restamps the button, then settles back', async () => {
        const write = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
        vi.stubGlobal('navigator', {clipboard: {write}});
        vi.stubGlobal('fetch', vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true, blob: () => Promise.resolve(new Blob([], {type: 'image/png'}))}));
        const w = paint();
        await w.find('button.take-home').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(write).toHaveBeenCalledTimes(1);
        expect(w.find('button.take-home').text()).toContain('Copied');
        await vi.advanceTimersByTimeAsync(2600);
        expect(w.find('button.take-home').text()).toBe('Copy image');
        w.unmount();
    });

    it('keeps the room\'s own acts after the take-home pair', async () => {
        vi.stubGlobal('navigator', {clipboard: {write: vi.fn<() => Promise<void>>()}});
        const run = vi.fn<() => void>();
        const w = paint({acts: [{label: 'Send to the stage →', run}]});
        const acts = w.findAll('.mount-acts .act').map(n => n.text());
        expect(acts).toStrictEqual(['Download ↓', 'Copy image', 'Send to the stage →']);
        await w.findAll('.mount-acts button').at(-1)?.trigger('click');
        expect(run).toHaveBeenCalledTimes(1);
        w.unmount();
    });
});
