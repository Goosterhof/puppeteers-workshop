import vue from '@vitejs/plugin-vue';
import {defineConfig} from 'vitest/config';

export default defineConfig({
    plugins: [vue()],
    test: {
        environment: 'jsdom',
        globals: true,
        include: ['tests/**/*.spec.ts'],
        setupFiles: ['./tests/setup.ts'],
        coverage: {
            provider: 'v8',
            // Without an explicit include, v8 measures only what a spec
            // imported — an unspecced room is absent from the table rather
            // than shown at zero, and the total reads as a flattering subset
            // (enhancement report #00009, P2-4). Name the whole source tree
            // so the instrument reports the surfaces nobody has covered yet.
            include: ['src/**/*.{ts,vue}'],
            // The bootstrap is three imports and a mount — it only ever runs
            // in a browser, so counting it would measure the shim, not the code.
            exclude: ['src/main.ts', 'src/env.d.ts'],
            reporter: ['text', 'html'],
        },
    },
});
