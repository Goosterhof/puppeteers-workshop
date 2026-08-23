// Bring your own still — the browser side of the footage shelf's upload door.
//
// The booth's stage door only admits JSON cue sheets (application/json, so a
// cross-site tab cannot fire it as a CORS simple request), so a still travels
// INSIDE the cue as base64 rather than as multipart. The server sniffs the
// bytes and names the file; the browser's job is only to read it faithfully.

export const STILL_TYPES = ['image/png', 'image/jpeg', 'image/webp'] as const;
export const STILL_ACCEPT = STILL_TYPES.join(',');

/** Is this something the shelf will take? Judged by the browser's type OR the
 *  extension — Windows hands over a `.webp` with an empty type more often than
 *  not, and the server's byte-sniff has the final word anyway. */
export function looksLikeStill(file: Pick<File, 'name' | 'type'>): boolean {
    if ((STILL_TYPES as readonly string[]).includes(file.type)) return true;
    return /\.(png|jpe?g|webp)$/i.test(file.name);
}

/** Bytes → base64, chunked so a 20 MB PNG never blows the argument stack. */
export function toBase64(bytes: Uint8Array): string {
    const CHUNK = 0x8000;
    let binary = '';
    for (let i = 0; i < bytes.length; i += CHUNK) {
        binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
    }
    return btoa(binary);
}

/** Read a File into the shape the upload window takes. */
export async function readStill(file: File): Promise<{name: string; data: string}> {
    const bytes = new Uint8Array(await file.arrayBuffer());
    return {name: file.name, data: toBase64(bytes)};
}
