// Phase 5 cutover sweep — the Vue front now answers at /; the graft path
// and the old set are gone. Full 11-tab pass on the :7901 sideport.
import {chromium} from 'playwright-core';

const exe = process.env.HOME + '/.cache/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell';
const OUT = process.env.SHOT_DIR || '/tmp';
const browser = await chromium.launch({executablePath: exe});
const errors = [];

const page = await browser.newPage({viewport: {width: 1700, height: 1200}});
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
await page.goto('http://127.0.0.1:7901/', {waitUntil: 'networkidle'});
await page.waitForTimeout(1000);

// the front at / is the Vue app (mounted #app), not the single-file era
console.log('/ serves Vue app:', await page.locator('#app main').count() === 1);
const stations = await page.locator('.station').evaluateAll(
    els => els.map(el => `${el.dataset.station}=${el.className.replace('station ', '')}`));
console.log('callboard:', stations.join(' '));

const tabs = await page.locator('nav [role=tab]').evaluateAll(els => els.map(el => el.dataset.tab));
console.log(`tabs (${tabs.length}):`, tabs.join(' '));
for (const t of tabs) {
    await page.locator(`nav [data-tab=${t}]`).click();
    await page.waitForTimeout(700);
    const visible = await page.locator(`#tab-${t}`).isVisible();
    const others = await page.locator('main > section:visible').count();
    if (!visible || others !== 1) errors.push(`TAB ${t}: visible=${visible} sections=${others}`);
    await page.screenshot({path: `${OUT}/cutover-${t}.png`});
}
await browser.close();

// route checks: the graft path is gone, the old vendor is gone
for (const [path, want] of [['/static/booth/index.html', 404], ['/static/vendor/three.module.min.js', 404],
    ['/', 200], ['/static/index.html', 200]]) {
    const res = await fetch(`http://127.0.0.1:7901${path}`);
    console.log(`${path} → ${res.status} (want ${want})${res.status === want ? '' : '  MISMATCH'}`);
    if (res.status !== want) errors.push(`ROUTE ${path}: ${res.status} != ${want}`);
}

console.log(errors.length ? errors.join('\n') : 'NO RUNTIME ERRORS');
