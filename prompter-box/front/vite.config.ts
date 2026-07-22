import vue from '@vitejs/plugin-vue';
import UnoCSS from 'unocss/vite';
import {fileURLToPath, URL} from 'node:url';
import {defineConfig} from 'vite';

// The Proscenium (#00063) — post-cutover build target.
//
// The stdlib Python server serves static/index.html at / and the whole
// static/ tree at /static/, so the built index.html lands at static/ root
// and every asset URL resolves under /static/ (`base`). `emptyOutDir` IS
// the strike: each build clears static/ so nothing but the built front
// (and its committed bundle) lives there.
//
// The dev server proxies API and file-shelf routes to the :7901 sideport —
// never the investor's :7900 booth (runbook §The Stagehands' Guard applies to
// verification traffic too). Boot it with verify-sideport.py.
const SIDEPORT = 'http://127.0.0.1:7901';

export default defineConfig({
    plugins: [vue(), UnoCSS()],
    base: '/static/',
    resolve: {alias: {'@': fileURLToPath(new URL('./src', import.meta.url))}},
    build: {
        outDir: '../static',
        emptyOutDir: true,
        // the lazy Potter's Wheel chunk carries three.js (~580 KB) — the same
        // weight the vendored era accepted; anything heavier should be seen
        chunkSizeWarningLimit: 700,
    },
    server: {
        port: 7902,
        strictPort: true,
        proxy: Object.fromEntries(
            ['/api', '/footage', '/face-output', '/stage-output', '/foley-output', '/kiln-output', '/pack-queue'].map(
                route => [route, SIDEPORT],
            ),
        ),
    },
});
