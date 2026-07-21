// Phase 4 acceptance sweep — the Kiln wing on the :7901 sideport, old vs
// new. List endpoints and wheel mounts only; nothing fires, nothing is
// approved, refired, discarded, or queued.
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

for (const [name, page] of [['old', oldPage], ['new', newPage]]) {
    // -- kiln: knobs + notes, no firing --
    await page.locator('nav [data-tab=kiln]').click();
    await page.waitForTimeout(300);
    await page.locator('details.kiln-settings summary').click();
    const notes = await page.locator('.knob-note').count();
    const octree = await page.locator('#kiln-octree').inputValue();
    const threshold = await page.locator('#kiln-threshold').inputValue();
    console.log(`${name} kiln: ${notes} knob-notes, octree=${octree}, threshold=${threshold}`);
    await page.screenshot({path: `${OUT}/${name}-kiln.png`});

    // -- rack: candidates + spotlight wheel --
    await page.locator('nav [data-tab=rack]').click();
    await page.waitForTimeout(900);
    const cards = await page.locator('#rack-grid .candidate').count();
    const badges = await page.locator('#rack-grid .qa-badge').allTextContents();
    console.log(`${name} rack: ${cards} candidates, badges=[${badges.join(' | ')}]`);
    if (cards) {
        await page.locator('#rack-grid .candidate .well').first().click();
        await page.waitForTimeout(2500); // the wheel chunk + GLB load
        const spot = await page.locator('#rack-view .candidate.spotlight').count();
        const canvas = await page.locator('#rack-view canvas.wheel-canvas').count();
        const spotlit = await page.locator('#rack-grid .candidate.spotlit').count();
        console.log(`${name} rack spotlight: card=${spot} wheel-canvas=${canvas} spotlit-in-grid=${spotlit}`);
        await page.screenshot({path: `${OUT}/${name}-rack.png`});
        const off = page.locator('#rack-view .acts .act', {hasText: 'Off the wheel'});
        if (await off.count()) await off.click();
    }

    // -- shelf: props + spotlight wheel --
    await page.locator('nav [data-tab=shelf]').click();
    await page.waitForTimeout(900);
    const props = await page.locator('#shelf-grid .candidate').count();
    console.log(`${name} shelf: ${props} props`);
    if (props) {
        await page.locator('#shelf-grid .well').first().click();
        await page.waitForTimeout(2500);
        const canvas = await page.locator('#shelf-view canvas.wheel-canvas').count();
        console.log(`${name} shelf spotlight: wheel-canvas=${canvas}`);
        await page.screenshot({path: `${OUT}/${name}-shelf.png`});
    }

    // -- night shift: call sheet, read-only --
    await page.locator('nav [data-tab=nightshift]').click();
    await page.waitForTimeout(900);
    const rows = await page.locator('#shift-rows .order').count();
    const startText = (await page.locator('#shift-start').textContent()).trim();
    console.log(`${name} night shift: ${rows} orders, start="${startText}"`);
    await page.screenshot({path: `${OUT}/${name}-shift.png`});
}

console.log(errors.length ? errors.join('\n') : 'NO RUNTIME ERRORS');
await browser.close();
