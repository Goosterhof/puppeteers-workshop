import {afterEach, describe, expect, it, vi} from 'vitest';
import {clipboardTakesImages, copyImageToClipboard, downloadName} from '../src/lib/take-home';

// Take it home: the filename a take lands under, and the clipboard copy.

describe('take-home', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('names the download after the take, decoded, never after the room', () => {
        expect(downloadName('/face-output/PrompterBox-001020_00001_.png')).toBe('PrompterBox-001020_00001_.png');
        expect(downloadName('/stage-output/crier%20bell.mp4?x=1')).toBe('crier bell.mp4');
        expect(downloadName('/foley-output/2026/take.flac')).toBe('take.flac');
        expect(downloadName('/')).toBe('take');
        expect(downloadName('/face-output/%E0%A4%A')).toBe('%E0%A4%A'); // a malformed escape is kept, not thrown
    });

    it('knows when the browser will not take an image', () => {
        vi.stubGlobal('navigator', {});
        expect(clipboardTakesImages()).toBe(false);
        vi.stubGlobal('navigator', {clipboard: {write: vi.fn<() => Promise<void>>()}});
        vi.stubGlobal('ClipboardItem', class {});
        expect(clipboardTakesImages()).toBe(true);
    });

    it('copies a PNG take to the clipboard as image/png', async () => {
        const write = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
        const items: Record<string, Blob>[] = [];
        vi.stubGlobal('navigator', {clipboard: {write}});
        vi.stubGlobal('ClipboardItem', class {
            constructor(parts: Record<string, Blob>) {
                items.push(parts);
            }
        });
        const png = new Blob([new Uint8Array([0x89, 0x50])], {type: 'image/png'});
        vi.stubGlobal('fetch', vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true, blob: () => Promise.resolve(png)}));

        await copyImageToClipboard('/face-output/x.png');
        expect(write).toHaveBeenCalledTimes(1);
        expect(items[0]?.['image/png']).toBe(png);
    });

    it('speaks in the booth\'s voice when the clipboard is shut or the take is gone', async () => {
        vi.stubGlobal('navigator', {});
        await expect(copyImageToClipboard('/face-output/x.png')).rejects.toThrow('use Download instead');
        vi.stubGlobal('navigator', {clipboard: {write: vi.fn<() => Promise<void>>()}});
        vi.stubGlobal('ClipboardItem', class {});
        vi.stubGlobal('fetch', vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: false, status: 404}));
        await expect(copyImageToClipboard('/face-output/gone.png')).rejects.toThrow('(404)');
    });
});
