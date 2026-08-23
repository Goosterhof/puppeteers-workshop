import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import StampedMount from '../src/components/StampedMount.vue';

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn<(path: string, body?: unknown) => Promise<unknown>>()}));
vi.mock('../src/composables/useBoothApi', () => ({api: apiMock}));

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
        expect(acts).toStrictEqual(['Download ↓', 'Copy image', 'Delete', 'Send to the stage →']);
        await w.findAll('.mount-acts button').at(-1)?.trigger('click');
        expect(run).toHaveBeenCalledTimes(1);
        w.unmount();
    });
});

describe('StampedMount — the bin', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        apiMock.mockReset();
        apiMock.mockResolvedValue({});
        // happy-dom's <dialog> has no showModal/close — stand them in
        HTMLDialogElement.prototype.showModal ??= function () {
            this.setAttribute('open', '');
        };
        HTMLDialogElement.prototype.close ??= function () {
            this.removeAttribute('open');
        };
    });
    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    const paint = (extra = {}) => mount(StampedMount, {props: {
        room: 'face', url: '/face-output/PrompterBox-001020_00001_.png', kind: 'image', title: 'a night watchman', ...extra,
    }});

    it('offers Delete for a take in a binnable room, and not for one the bin refuses', () => {
        const w = paint();
        expect(w.find('button.take-bin-act').text()).toBe('Delete');
        w.unmount();
        const k = paint({url: '/kiln-output/omafiets/paint.png'});
        expect(k.find('button.take-bin-act').exists()).toBe(false);
        k.unmount();
    });

    it('asks first — Keep it bins nothing', async () => {
        const w = paint();
        await w.find('button.take-bin-act').trigger('click');
        expect(w.find('dialog.take-bin').attributes('open')).toBeDefined();
        expect(w.find('.bin-subject').text()).toBe('PrompterBox-001020_00001_.png');
        await w.find('.bin-keep').trigger('click');
        expect(apiMock).not.toHaveBeenCalledWith('/api/take/discard', expect.anything());
        expect(w.emitted('binned')).toBeUndefined();
        w.unmount();
    });

    it('Bin it cues the discard with the room and name, re-reads the shelves, and tells the room', async () => {
        const w = paint();
        await w.find('button.take-bin-act').trigger('click');
        await w.find('.bin-confirm').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(apiMock).toHaveBeenCalledWith('/api/take/discard', {room: 'face', name: 'PrompterBox-001020_00001_.png'});
        expect(apiMock).toHaveBeenCalledWith('/api/archive');
        expect(w.emitted('binned')).toStrictEqual([['/face-output/PrompterBox-001020_00001_.png']]);
        w.unmount();
    });

    it('a shelved still re-reads the footage strip instead of the archive', async () => {
        const w = paint({url: '/footage/sitter.png', room: 'face'});
        apiMock.mockImplementation((path: string) => Promise.resolve(path === '/api/footage' ? {images: []} : {}));
        await w.find('button.take-bin-act').trigger('click');
        await w.find('.bin-confirm').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(apiMock).toHaveBeenCalledWith('/api/take/discard', {room: 'footage', name: 'sitter.png'});
        expect(apiMock).toHaveBeenCalledWith('/api/footage');
        expect(apiMock).not.toHaveBeenCalledWith('/api/archive');
        w.unmount();
    });

    it('the booth\'s refusal restamps the button and the print stays', async () => {
        apiMock.mockRejectedValueOnce(new Error('That take is not hanging in that room — nothing to bin.'));
        const w = paint();
        await w.find('button.take-bin-act').trigger('click');
        await w.find('.bin-confirm').trigger('click');
        await vi.advanceTimersByTimeAsync(0);
        expect(w.find('button.take-bin-act').text()).toContain('nothing to bin');
        expect(w.emitted('binned')).toBeUndefined();
        await vi.advanceTimersByTimeAsync(3100);
        expect(w.find('button.take-bin-act').text()).toBe('Delete');
        w.unmount();
    });
});
