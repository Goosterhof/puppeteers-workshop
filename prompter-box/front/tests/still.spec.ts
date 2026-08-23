import {describe, expect, it} from 'vitest';
import {looksLikeStill, readStill, toBase64} from '../src/lib/still';

// The browser half of bring-your-own-still: judge what the shelf will take,
// and hand the bytes over whole.

describe('still', () => {
    it('judges a still by the browser type OR the extension — Windows drops types', () => {
        expect(looksLikeStill({name: 'x.bin', type: 'image/png'})).toBe(true);
        expect(looksLikeStill({name: 'sitter.WEBP', type: ''})).toBe(true);
        expect(looksLikeStill({name: 'sitter.jpeg', type: ''})).toBe(true);
        expect(looksLikeStill({name: 'take.mp4', type: 'video/mp4'})).toBe(false);
        expect(looksLikeStill({name: 'notes.txt', type: 'text/plain'})).toBe(false);
    });

    it('encodes bytes to base64 the same way the platform does, chunk boundaries included', () => {
        const bytes = new Uint8Array(0x8000 * 2 + 7);
        for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 31) & 0xff;
        const expected = btoa(Array.from(bytes, b => String.fromCharCode(b)).join(''));
        expect(toBase64(bytes)).toBe(expected);
        expect(toBase64(new Uint8Array())).toBe('');
    });

    it('reads a File into the name + base64 shape the upload window takes', async () => {
        const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3]);
        const file = new File([png], 'sitter.png', {type: 'image/png'});
        expect(await readStill(file)).toStrictEqual({name: 'sitter.png', data: btoa(String.fromCharCode(...png))});
    });
});
