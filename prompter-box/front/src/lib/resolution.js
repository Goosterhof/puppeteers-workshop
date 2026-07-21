// The Stage's resolution grammar — presets per performer kind and the
// aspect matcher that follows a cast lead (the old matchResolution).

export const RES_PRESETS = {
    video: ['704x1280', '480x832', '1280x704', '832x480', '1280x720', '720x1280'],
    image: ['1024x1024', '832x1216', '1216x832', '1280x720', '720x1280'],
};

export function nearestResolution(options, w, h) {
    const dist = v => {
        const [ow, oh] = v.split('x').map(Number);
        return Math.abs(Math.log((w / h) / (ow / oh)));
    };
    return options.reduce((a, b) => (dist(b) < dist(a) ? b : a));
}
