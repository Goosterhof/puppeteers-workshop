// Phase 2 acceptance sweep — the Canisters, Foley Booth, and house iframes
// on the :7901 sideport, old front vs new.
import {chromium} from 'playwright-core';

const exe = process.env.HOME + '/.cache/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell';
const OUT = process.env.SHOT_DIR || '/tmp';
const browser = await chromium.launch({executablePath: exe});
const errors = [];

const boot = async url => {
    const page = await browser.newPage({viewport: {width: 1700, height: 1100}});
    page.on('pageerror', e => errors.push(`PAGEERROR ${url}: ${e.message}`));
    await page.goto(url, {waitUntil: 'networkidle'});
    await page.waitForTimeout(800);
    return page;
};

const oldPage = await boot('http://127.0.0.1:7901/');
const newPage = await boot('http://127.0.0.1:7901/static/booth/index.html');

// -- the Canisters: grid parity, then the 4 interactions on the new front --
for (const [name, page] of [['old', oldPage], ['new', newPage]]) {
    await page.locator('nav [data-tab=archive]').click();
    await page.waitForTimeout(900);
    const count = await page.locator('#arch-grid .canister').count();
    const line = (await page.locator('#arch-count').textContent()).trim();
    console.log(`${name} archive: ${count} canisters — "${line}"`);
    await page.screenshot({path: `${OUT}/${name}-archive.png`});
}

const search = newPage.locator('#arch-search');
await search.fill('seed7');
await newPage.waitForTimeout(300);
const oldSearch = oldPage.locator('#arch-search');
await oldSearch.fill('seed7');
await oldSearch.dispatchEvent('input');
await oldPage.waitForTimeout(300);
console.log('search "seed7": old', await oldPage.locator('#arch-grid .canister').count(),
    '| new', await newPage.locator('#arch-grid .canister').count());
await search.fill('');
await oldSearch.fill('');
await oldSearch.dispatchEvent('input');

for (const [sel, label] of [['#arch-rooms, .pills', 'room'], ['#arch-kinds, .pills', 'kind']]) void sel; // labels only

// room pill: Stage — old uses #arch-rooms buttons, new uses FilterPills
await oldPage.locator('#arch-rooms button', {hasText: 'Stage'}).click();
await newPage.locator('.pills button', {hasText: 'Stage'}).first().click();
await newPage.waitForTimeout(300);
console.log('room=stage: old', await oldPage.locator('#arch-grid .canister').count(),
    '| new', await newPage.locator('#arch-grid .canister').count());

// kind pill: Stills
await oldPage.locator('#arch-kinds button', {hasText: 'Stills'}).click();
await newPage.locator('.pills button', {hasText: 'Stills'}).click();
await newPage.waitForTimeout(300);
console.log('room=stage kind=image: old', await oldPage.locator('#arch-grid .canister').count(),
    '| new', await newPage.locator('#arch-grid .canister').count());

// reset pills, then click-to-mount the first canister on both
for (const page of [oldPage, newPage]) {
    await page.locator('#arch-rooms button, .pills button', {hasText: 'All'}).first().click().catch(() => {});
}
await oldPage.locator('#arch-rooms button').first().click();
await oldPage.locator('#arch-kinds button').first().click();
const newPills = newPage.locator('.pills');
await newPills.nth(0).locator('button').first().click();
await newPills.nth(1).locator('button').first().click();
await newPage.waitForTimeout(300);

for (const [name, page] of [['old', oldPage], ['new', newPage]]) {
    await page.locator('#arch-grid .canister').first().click();
    await page.waitForTimeout(600);
    const hasMedia = await page.locator('#arch-view img, #arch-view video, #arch-view audio').count();
    const cap = (await page.locator('#arch-view .cap').textContent()).trim();
    const actLabels = await page.locator('#arch-view .cast').allTextContents();
    console.log(`${name} mount: media=${hasMedia} acts=[${actLabels.join(' | ')}] cap="${cap.slice(0, 80)}…"`);
    await page.screenshot({path: `${OUT}/${name}-arch-mount.png`});
}

// -- the Foley Booth: form parity + sources shelf --
for (const [name, page] of [['old', oldPage], ['new', newPage]]) {
    await page.locator('nav [data-tab=foley]').click();
    await page.waitForTimeout(500);
    const groups = await page.locator('#foley-video optgroup').evaluateAll(els =>
        els.map(g => `${g.label}(${g.children.length})`));
    console.log(`${name} foley reels: ${groups.join(' ') || 'none'}`);
    await page.screenshot({path: `${OUT}/${name}-foley.png`});
}

// -- the house iframes: cold until first entry, warm after --
for (const tab of ['house-stage', 'house-face']) {
    const before = await newPage.locator(`#tab-${tab} iframe`).getAttribute('src');
    await newPage.locator(`nav [data-tab=${tab}]`).click();
    await newPage.waitForTimeout(300);
    const after = await newPage.locator(`#tab-${tab} iframe`).getAttribute('src');
    console.log(`${tab}: src before entry=${JSON.stringify(before)} after=${JSON.stringify(after)}`);
}

console.log(errors.length ? errors.join('\n') : 'NO RUNTIME ERRORS');
await browser.close();
