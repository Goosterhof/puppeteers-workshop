// The Stage's resolution grammar — presets per performer kind and the
// aspect matcher that follows a cast lead (the old matchResolution).

export const RES_PRESETS: Record<'video' | 'image', string[]> = {
    video: ['704x1280', '480x832', '1280x704', '832x480', '1280x720', '720x1280'],
    image: ['1024x1024', '832x1216', '1216x832', '1280x720', '720x1280'],
};

export function nearestResolution(options: string[], w: number, h: number): string {
    const dist = (v: string): number => {
        const [ow = 1, oh = 1] = v.split('x').map(Number);
        return Math.abs(Math.log((w / h) / (ow / oh)));
    };
    return options.reduce((a, b) => (dist(b) < dist(a) ? b : a));
}
