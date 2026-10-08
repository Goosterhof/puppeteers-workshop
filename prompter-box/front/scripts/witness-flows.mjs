// Dev-only browser witness. Serves the committed bundle through Playwright
// route fulfillment: no booth, models, GPU jobs, or investor assets are changed.
import {chromium} from 'playwright-core';
import {readFile, mkdir, mkdtemp, readdir, access} from 'node:fs/promises';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {homedir, tmpdir} from 'node:os';
import assert from 'node:assert/strict';

const root = dirname(dirname(dirname(dirname(fileURLToPath(import.meta.url)))));
const out = process.env.WORKSHOP_WITNESS_OUT || await mkdtemp(join(tmpdir(), 'workshop-flow-witness-'));
await mkdir(out, {recursive: true});
async function browserPath() {
    if (process.env.WORKSHOP_BROWSER) return process.env.WORKSHOP_BROWSER;
    const cache = join(homedir(), '.cache/ms-playwright');
    const names = (await readdir(cache)).filter(n => n.startsWith('chromium_headless_shell-')).sort((a, b) => Number(b.split('-').at(-1)) - Number(a.split('-').at(-1)));
    for (const name of names) {
        const bin = join(cache, name, 'chrome-headless-shell-linux64/chrome-headless-shell');
        try { await access(bin); return bin; } catch { /* Try the next installed binary. */ }
    }
    throw new Error('Set WORKSHOP_BROWSER to an installed Chromium binary.');
}
const portrait = (grin = false) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 520"><rect width="400" height="520" fill="#38262e"/><path d="M68 510 Q80 340 200 350 Q325 330 342 510" fill="#673b55"/><path d="M104 263 Q60 82 197 58 Q347 79 298 310 L267 256 L200 335 L123 267" fill="#281b23"/><ellipse cx="200" cy="206" rx="82" ry="112" fill="#d4a282"/><path d="M125 103 L89 27 L172 83 M232 79 L307 30 L279 120" fill="#a59b76"/><path d="M122 164 Q150 144 171 168 M230 167 Q256 143 280 160" fill="none" stroke="#412434" stroke-width="9"/><ellipse cx="153" cy="183" rx="7" ry="6" fill="#25212b"/><ellipse cx="250" cy="182" rx="7" ry="6" fill="#25212b"/><path d="${grin ? 'M150 252 Q204 298 270 233' : 'M171 253 Q206 267 242 246'}" fill="none" stroke="#643743" stroke-width="9"/><text x="200" y="485" text-anchor="middle" fill="#f5e7c9" font-family="serif" font-size="19">${grin ? 'A sharper grin' : 'The original character'}</text></svg>`;
const sourceImage = process.env.WORKSHOP_REFERENCE ? await readFile(process.env.WORKSHOP_REFERENCE) : Buffer.from(portrait());
const resultImage = process.env.WORKSHOP_RESULT ? await readFile(process.env.WORKSHOP_RESULT) : Buffer.from(portrait(true));
const imageType = process.env.WORKSHOP_REFERENCE ? 'image/webp' : 'image/svg+xml';
const models = {models: [
    {type: 'wan-i2v', name: 'Wan 2.2 Lightning', kind: 'i2v', resolution: '704x1280', video_length: 41, steps: 4, guidance: 1, loras: [], note: 'The house motion recipe'},
    {type: 'wan-t2v', name: 'Wan 5B', kind: 't2v', resolution: '1280x720', video_length: 41, steps: 8, guidance: 1, loras: []},
    {type: 'scail', name: 'SCAIL-2', kind: 'swap', resolution: '480x832', video_length: 81, steps: 20, guidance: 5, loras: []},
    {type: 'krea', name: 'Krea 2', kind: 't2i', resolution: '1024x1024', video_length: 1, steps: 28, guidance: 4.5, loras: []},
], default: 'wan-i2v'};
const browser = await chromium.launch({executablePath: await browserPath(), args: ['--enable-unsafe-swiftshader']});
let groups = 0;
try {
    for (const width of [1440, 1000]) {
        const context = await browser.newContext({viewport: {width, height: 1000}, reducedMotion: 'reduce'});
        const page = await context.newPage();
        const errors = [];
        const posts = [];
        let painted = false;
        let holdPainting = false;
        page.on('pageerror', e => errors.push(e.message));
        await page.route('**/*', async route => {
            const req = route.request();
            const url = new URL(req.url());
            const path = url.pathname;
            const json = value => route.fulfill({contentType: 'application/json', body: JSON.stringify(value)});
            if (req.method() === 'POST') {
                const body = req.postDataJSON();
                posts.push({path, body});
                if (path === '/api/face/generate') { painted = true; return json({prompt_id: 'fixture-paint'}); }
                if (path === '/api/stage/cast') return json({cast: 'refined.png'});
                if (path === '/api/queue/add') return json({ok: true});
                return json({ok: true});
            }
            if (path === '/api/status') return json({forge: {up: true, loaded: []}, face_shop: {up: true, vram_free_gb: 28, vram_total_gb: 32}, stage_job: {state: 'idle'}, stage_ui: {up: false}, foley: {installed: true}, kiln: {job_state: 'idle'}});
            if (path === '/api/footage') return json({images: ['character.png', ...(painted ? ['refined.png'] : [])]});
            if (path === '/api/stage/models') return json(models);
            if (path === '/api/face/models') return json({painters: ['flux-2-klein-9b.gguf'], default: 'flux-2-klein-9b.gguf'});
            if (path === '/api/forge/models') return json({models: []});
            if (path === '/api/foley/sources') return json({stage: ['motion.mp4'], footage: []});
            if (path === '/api/archive') return json({face: painted ? [{name: 'refined.png', kind: 'image', mtime: Date.now()/1000, meta: {prompt: 'sharpen the grin', model: 'flux-2-klein-9b', seed: 7}}, ...Array.from({length: 20}, (_, i) => ({name: `older-${i}.png`, kind: 'image', mtime: Date.now()/1000-i-1, meta: {prompt: 'keep the character and costume while changing the expression; compare the silhouette and lighting before choosing this take', model: 'flux-2-klein-9b', seed: i}}))] : [], stage: [], foley: []});
            if (path.startsWith('/api/face/result/')) return json(holdPainting ? {state: 'painting'} : {state: 'done', images: ['refined.png']});
            if (path === '/api/pins') return json({pins: Array.from({length: 12}, (_, i) => ({id: `pin-${i}`, name: `Proven face ${i}`, room: 'face', recipe: {prompt: 'a proven cue', seed: i, model: 'flux-2-klein-9b'}}))});
            if (path === '/api/rack/list') return json({candidates: []});
            if (path === '/api/shelf/list') return json({props: []});
            if (path === '/api/queue/list') return json({rows: [], shift: {running: false}});
            if (path.endsWith('/job')) return json({state: 'idle'});
            if (path.startsWith('/api/')) throw new Error(`Unfixtured read: ${path}`);
            if (path.startsWith('/footage/')) return route.fulfill({contentType: imageType, body: path.includes('refined') ? resultImage : sourceImage});
            if (path.startsWith('/face-output/')) return route.fulfill({contentType: imageType, body: resultImage});
            if (url.hostname !== 'workshop.test') return route.fulfill({contentType: 'text/html', body: '<p>Native machine console — fixture</p>'});
            const file = path === '/' ? 'index.html' : path.replace(/^\/static\//, '');
            const type = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html';
            return route.fulfill({contentType: type, body: await readFile(join(root, 'prompter-box/static', file))});
        });
        await page.goto('http://workshop.test/');
        await page.locator('[data-tab="face"]').click();
        await page.getByRole('button', {name: 'Refine a character', exact: true}).click();
        await page.locator('#face-thumbs img').first().click();
        await page.locator('#face-prompt').fill('sharpen the grin');
        await page.locator('#face-keep').fill('hair, clothes and pose');
        await page.locator('#face-go').click();
        await page.locator('.face-comparison .mount').waitFor();
        assert.equal(posts.filter(p => p.path === '/api/face/generate').length, 1);
        assert.equal(posts.find(p => p.path === '/api/face/generate').body.source, 'character.png');
        assert.match(posts.find(p => p.path === '/api/face/generate').body.prompt, /Keep unchanged: hair, clothes and pose/);
        await page.locator('.deck').evaluate(el => { el.scrollTop = 0; });
        await page.screenshot({path: join(out, `face-compare-${width}.png`)});
        await page.getByRole('button', {name: 'Refine this version →', exact: true}).click();
        await page.waitForFunction(() => document.querySelector('.character-source figcaption')?.textContent === 'refined.png');
        assert.equal(await page.locator('.revision-strip .revision').count(), 2);
        await page.reload();
        await page.locator('[data-tab="face"]').click();
        await page.locator('.face-comparison .mount').waitFor();
        assert.equal(posts.filter(p => p.path === '/api/face/generate').length, 1);
        assert.equal(await page.locator('.revision-strip .revision').count(), 2);
        groups++;
        // A previous still-painting task must not turn Animate into another still.
        await page.locator('[data-tab="stage"]').click();
        await page.getByRole('button', {name: 'Advanced still painter', exact: true}).click();
        await page.locator('#stage-prompt').fill('the character gives a small bow');
        await page.locator('[data-tab="face"]').click();
        await page.getByRole('button', {name: 'Animate this version →', exact: true}).click();
        await page.waitForFunction(() => document.querySelector('#stage-task button[aria-pressed="true"]')?.textContent === 'Animate a still');
        assert.equal(await page.locator('#stage-prompt').inputValue(), 'the character gives a small bow');
        const tabs = await page.locator('.rail .tab').evaluateAll(nodes => nodes.map(n => n.dataset.tab));
        assert.equal(tabs.length, 11);
        for (const tab of tabs) {
            await page.locator(`[data-tab="${tab}"]`).click();
            const panel = page.locator(`#panel-${tab}`);
            assert.ok((await panel.locator('.room-flow h2').innerText()).length > 8);
            assert.ok(await panel.locator('.room-flow nav button').count() >= 3);
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${tab} overflows at ${width}`);
            const overflow = await panel.evaluate(el => el.scrollWidth > el.clientWidth + 1);
            if (overflow) {
                await page.screenshot({path: join(out, `overflow-${tab}-${width}.png`)});
                console.log(await panel.evaluate(el => { const r = el.getBoundingClientRect(); return [...el.querySelectorAll('*')].filter(n => n.getBoundingClientRect().right > r.right + 1).map(n => [n.tagName, n.id, n.className, n.getBoundingClientRect().width]).slice(0, 8); }));
            }
            assert.equal(overflow, false, `${tab} content overflows at ${width}`);
        }
        groups++;
        await page.locator('[data-tab="stage"]').click();
        await page.getByRole('button', {name: 'Transfer motion', exact: true}).click();
        await page.locator('.room-flow button', {hasText: 'Motion brief'}).click();
        assert.equal(await page.locator('#stage-prompt').evaluate(el => el === document.activeElement), true);
        await page.locator('[data-tab="nightshift"]').click();
        await page.getByRole('button', {name: 'A list of different props', exact: true}).click();
        await page.locator('#shift-subject').fill('a copper kettle\na wooden ladder');
        await page.locator('#shift-add').click();
        assert.deepEqual(posts.find(p => p.path === '/api/queue/add').body.subject, ['a copper kettle', 'a wooden ladder']);
        groups++;
        await page.locator('[data-tab="archive"]').click();
        await page.locator('.deck').evaluate(el => { el.scrollTop = 0; });
        await page.locator('.canister').first().evaluate(el => el.click());
        await page.locator('.bench .mount-frame img').waitFor();
        await page.locator('.bench .mount-frame img').evaluate(async img => { await img.decode(); });
        const readPrint = () => page.locator('.bench').evaluate(el => ({
            picture: el.querySelector('img').getBoundingClientRect().height,
            budget: Number.parseFloat(getComputedStyle(el.closest('.light-table')).getPropertyValue('--bench-media-height')),
            acts: el.querySelector('.mount-acts').getBoundingClientRect().bottom,
            limit: document.querySelector('.deck').getBoundingClientRect().bottom,
        }));
        const geometry = await readPrint();
        await page.screenshot({path: join(out, `canisters-actions-${width}.png`)});
        assert.ok(geometry.picture >= 120 && geometry.acts <= geometry.limit, `Canisters picture/actions hidden with 12 pins at ${width}: ${JSON.stringify(geometry)}`);
        await page.getByRole('button', {name: 'Pin this recipe…', exact: true}).click();
        const naming = page.locator('dialog.pin-naming[open]');
        await naming.waitFor();
        assert.ok(await naming.evaluate(el => el.getBoundingClientRect().bottom <= innerHeight));
        await naming.getByRole('button', {name: 'Cancel', exact: true}).click();
        const scroll = await page.locator('.deck').evaluate(el => el.scrollTop);
        // Playwright's actionability scroll would move a narrow folded shelf
        // before a second click. Dispatch the mount itself to measure the app.
        await page.locator('.canister').first().evaluate(el => el.click());
        assert.equal(await page.locator('.deck').evaluate(el => el.scrollTop), scroll);
        // A changed caption/media height must also preserve a reader's place
        // halfway down a real shelf, after ResizeObserver and layout settle.
        await page.locator('.deck').evaluate(el => { el.scrollTop = 900; });
        const deepScroll = await page.locator('.deck').evaluate(el => el.scrollTop);
        assert.ok(deepScroll > 0);
        await page.locator('.canister').nth(1).evaluate(el => el.click());
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        assert.equal(await page.locator('.deck').evaluate(el => el.scrollTop), deepScroll, `Mount moved the shelf at ${width}`);
        const deepPrint = await readPrint();
        await page.locator('.deck').evaluate(el => { el.scrollTop = 0; });
        const backPrint = await readPrint();
        assert.equal(deepPrint.budget, backPrint.budget, `Print size depended on scroll at ${width}`);
        assert.ok(backPrint.picture >= 120 && backPrint.acts <= backPrint.limit, `Print disappeared after returning to top at ${width}`);
        // A completion on another tab must never open an invisible modal.
        await page.locator('[data-tab="face"]').click();
        await page.locator('#face-prompt').fill('another painted change');
        holdPainting = true;
        await page.locator('#face-go').click();
        await page.locator('#face-abandon').waitFor();
        await page.locator('[data-tab="archive"]').click();
        await page.getByRole('button', {name: 'Refine this character →', exact: true}).click();
        await page.locator('#face-prompt').fill('a cue edited while the replacement waits');
        await page.locator('[data-tab="stage"]').click();
        holdPainting = false;
        await page.waitForFunction(() => !document.querySelector('#face-abandon'));
        assert.equal(await page.locator('#panel-face dialog[open]').count(), 0);
        await page.locator('[data-tab="forge"]').click();
        await page.locator('#panel-forge').waitFor({state: 'visible'});
        await page.locator('[data-tab="face"]').click();
        await page.locator('#face-new-dialog[open]').waitFor({state: 'visible'});
        await page.getByRole('button', {name: 'Keep this character', exact: true}).click();
        assert.equal(await page.locator('#face-prompt').inputValue(), 'a cue edited while the replacement waits');
        // A known version needs no reset dialog and keeps a later typed cue.
        holdPainting = true;
        await page.locator('#face-go').click();
        await page.locator('#face-abandon').waitFor();
        await page.locator('[data-tab="archive"]').click();
        await page.locator('.canister').first().evaluate(el => el.click());
        await page.getByRole('button', {name: 'Refine this character →', exact: true}).click();
        await page.locator('#face-prompt').fill('the next change typed during painting');
        await page.locator('[data-tab="stage"]').click();
        holdPainting = false;
        await page.waitForFunction(() => !document.querySelector('#face-abandon'));
        await page.locator('[data-tab="face"]').click();
        assert.equal(await page.locator('#panel-face dialog[open]').count(), 0);
        assert.equal(await page.locator('#face-prompt').inputValue(), 'the next change typed during painting');
        groups++;
        await page.locator('[data-tab="archive"]').click();
        await page.locator('.canister').nth(1).evaluate(el => el.click());
        await page.getByRole('button', {name: 'Refine this character →', exact: true}).click();
        await page.locator('#panel-face').waitFor({state: 'visible'});
        await page.getByRole('button', {name: 'Start new bench', exact: true}).click();
        groups++;
        assert.deepEqual(errors, []);
        await context.close();
    }
    console.log(`${groups} browser groups passed; 11 tabs at 1440 and 1000px. Screenshots: ${out}`);
} finally { await browser.close(); }
