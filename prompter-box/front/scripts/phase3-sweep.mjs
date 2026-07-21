// Phase 3 acceptance sweep — Forge, Stage, Face Shop forms on the :7901
// sideport, old front vs new. List endpoints only; no GPU firing.
import {chromium} from 'playwright-core';

const exe = process.env.HOME + '/.cache/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell';
const OUT = process.env.SHOT_DIR || '/tmp';
const browser = await chromium.launch({executablePath: exe});
const errors = [];

const boot = async url => {
    const page = await browser.newPage({viewport: {width: 1700, height: 1200}});
    page.on('pageerror', e => errors.push(`PAGEERROR ${url}: ${e.message}`));
    await page.goto(url, {waitUntil: 'networkidle'});
    await page.waitForTimeout(900);
    return page;
};

const oldPage = await boot('http://127.0.0.1:7901/');
const newPage = await boot('http://127.0.0.1:7901/static/booth/index.html');

const options = (page, sel) => page.locator(`${sel} option`).allTextContents()
    .then(o => o.map(t => t.trim()).join(' | '));

for (const [name, page] of [['old', oldPage], ['new', newPage]]) {
    // -- forge --
    await page.locator('nav [data-tab=forge]').click();
    await page.waitForTimeout(400);
    console.log(`${name} forge voices: [${await options(page, '#forge-model')}]`);
    console.log(`${name} forge thumbs: ${await page.locator('#forge-thumbs img').count()}`);
    await page.screenshot({path: `${OUT}/${name}-forge.png`});

    // -- stage --
    await page.locator('nav [data-tab=stage]').click();
    await page.waitForTimeout(600);
    console.log(`${name} playbill: [${await options(page, '#stage-model')}]`);
    const knobs = {};
    for (const id of ['stage-res', 'stage-len', 'stage-steps', 'stage-guidance', 'stage-seed']) {
        knobs[id] = await page.locator(`#${id}`).inputValue();
    }
    console.log(`${name} knobs: ${JSON.stringify(knobs)}`);
    console.log(`${name} wardrobe: [${(await page.locator('#stage-loras .garment button').allTextContents()).join(' | ')}]`);
    console.log(`${name} lead label: ${(await page.locator('#stage-lead-label').textContent()).trim()}`);
    // the refusal voice — no lead picked, no server call
    await page.locator('#stage-go').click();
    await page.waitForTimeout(200);
    console.log(`${name} refusal: ${(await page.locator('#tab-stage .error, #stage-error').first().textContent()).trim()}`);
    await page.screenshot({path: `${OUT}/${name}-stage.png`});

    // -- face --
    await page.locator('nav [data-tab=face]').click();
    await page.waitForTimeout(400);
    console.log(`${name} painters: [${await options(page, '#face-model')}]`);
    const wBefore = await page.locator('#face-w').isDisabled();
    await page.locator('#face-thumbs img').first().click();
    await page.waitForTimeout(150);
    const wAfter = await page.locator('#face-w').isDisabled();
    await page.locator('#face-thumbs img').first().click(); // unpick again
    console.log(`${name} sitter lock: w disabled before=${wBefore} after-pick=${wAfter}`);
    await page.screenshot({path: `${OUT}/${name}-face.png`});
}

// cross-room wire on the new front: performer switch to SCAIL reveals choreography
await newPage.locator('nav [data-tab=stage]').click();
const playbill = await newPage.locator('#stage-model option').evaluateAll(els => els.map(o => o.value));
const swap = playbill.find(v => /scail|vace|swap/i.test(v));
if (swap) {
    await newPage.locator('#stage-model').selectOption(swap);
    await newPage.waitForTimeout(500);
    const guideVisible = await newPage.locator('#stage-guide-row').isVisible();
    const guideGroups = await newPage.locator('#stage-guide optgroup').evaluateAll(els => els.map(g => `${g.label}(${g.children.length})`));
    console.log(`new swap performer: guide row visible=${guideVisible} groups=${guideGroups.join(' ')}`);
}

console.log(errors.length ? errors.join('\n') : 'NO RUNTIME ERRORS');
await browser.close();
