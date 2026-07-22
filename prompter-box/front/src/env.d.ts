/// <reference types="vite/client" />

// The reduced-motion rehearsal switch — tests/setup.ts wires window.matchMedia
// to this flag so a spec can flip the preference without a real media query.
declare global {
    // eslint-disable-next-line no-var
    var __reducedMotion: boolean;
}

export {};
