// Take it home — the two ways a mounted take leaves the booth for the
// Windows side of the glass (2026-08-23). The file already lives on the
// bench's disk, but "on the bench" is a WSL path the investor would have to
// go digging for; a browser download lands it in Downloads, and a clipboard
// copy puts it straight into the next app.

/** The filename a take should land under: the URL's last segment, decoded —
 *  `/face-output/PrompterBox-001020_00001_.png` → `PrompterBox-001020_00001_.png`. */
export function downloadName(url: string): string {
    const last = url.split('?')[0]?.split('/').filter(Boolean).pop() ?? '';
    try {
        return decodeURIComponent(last) || 'take';
    } catch {
        return last || 'take';
    }
}

/** Whatever the image was encoded as, the clipboard only takes PNG — so a
 *  JPEG or WebP take is redrawn onto a canvas first. */
async function asPngBlob(blob: Blob): Promise<Blob> {
    if (blob.type === 'image/png') return blob;
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0);
    return new Promise<Blob>((resolve, reject) => {
        canvas.toBlob(b => {
            if (b) resolve(b);
            else reject(new Error('The canvas gave nothing back.'));
        }, 'image/png');
    });
}

export function clipboardTakesImages(): boolean {
    return typeof navigator !== 'undefined' && !!navigator.clipboard?.write && typeof ClipboardItem !== 'undefined';
}

/** Copy an image take to the clipboard as PNG. Throws in the booth's voice
 *  when the browser will not take it (no secure context, permission refused). */
export async function copyImageToClipboard(url: string): Promise<void> {
    if (!clipboardTakesImages()) {
        throw new Error('This browser keeps its clipboard shut to the booth — use Download instead.');
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error(`The take could not be fetched for copying (${res.status}).`);
    const png = await asPngBlob(await res.blob());
    await navigator.clipboard.write([new ClipboardItem({'image/png': png})]);
}

// -- the bin --------------------------------------------------------------

export type BinRoom = 'face' | 'stage' | 'foley' | 'footage';

const ROOM_BY_PREFIX: Record<string, BinRoom> = {
    '/face-output/': 'face',
    '/stage-output/': 'stage',
    '/foley-output/': 'foley',
    '/footage/': 'footage',
};

/** Where a mounted take hangs, read off its URL — the room the bin window
 *  takes and the name inside that room (decoded, subdirs kept for Foley).
 *  Null for anything the bin does not take (kiln pieces, static, foreign). */
export function takeLocation(url: string): {room: BinRoom; name: string} | null {
    const path = url.split('?')[0] ?? '';
    for (const [prefix, room] of Object.entries(ROOM_BY_PREFIX)) {
        if (path.startsWith(prefix)) {
            const rest = path.slice(prefix.length);
            if (!rest) return null;
            try {
                return {room, name: decodeURIComponent(rest)};
            } catch {
                return {room, name: rest};
            }
        }
    }
    return null;
}
