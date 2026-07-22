import {describe, expect, it} from 'vitest';
import {nearestResolution, RES_PRESETS} from '../src/lib/resolution';

// The Stage's aspect matcher — a cast lead picks the preset whose aspect
// ratio is nearest on the log scale (the old matchResolution).

describe('nearestResolution', () => {
    it('a portrait lead lands on the nearest portrait preset', () => {
        expect(nearestResolution(RES_PRESETS.video, 1080, 1920)).toBe('720x1280');
        expect(nearestResolution(RES_PRESETS.video, 768, 1344)).toBe('480x832');
    });

    it('a landscape lead lands on a landscape preset', () => {
        expect(nearestResolution(RES_PRESETS.video, 1920, 1080)).toBe('1280x720');
    });

    it('a square lead on the image presets stays square', () => {
        expect(nearestResolution(RES_PRESETS.image, 1024, 1024)).toBe('1024x1024');
    });

    it('an exact aspect match wins outright', () => {
        expect(nearestResolution(['480x832', '832x480'], 480, 832)).toBe('480x832');
    });
});
