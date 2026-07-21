// Phase 1 acceptance sweep — old front vs new front on the :7901 sideport.
import {chromium} from 'playwright-core';

const exe = process.env.HOME + '/.cache/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell';
const OUT = '/tmp/claude-1000/-home-goosterhof-code-video-lab/7dc99f0f-724e-4855-82fe-90b16edfc0d0/scratchpad';
const browser = await chromium.launch({executablePath: exe});
const errors = [];

// -- old front: callboard reference --
const oldPage = await browser.newPage({viewport: {width: 1700, height: 1000}});
oldPage.on('pageerror', e => errors.push('OLD PAGEERROR: ' + e.message));
await oldPage.goto('http://127.0.0.1:7901/', {waitUntil: 'networkidle'});
await oldPage.waitForTimeout(1200);
const oldBoard = await oldPage.locator('#callboard').boundingBox();
await oldPage.screenshot({path: OUT + '/old-callboard.png', clip: oldBoard});
const oldStates = await oldPage.locator('.station').evaluateAll(
    els => els.map(el => `${el.dataset.station}=${el.className.replace('station ', '')}`));
const oldOcc = await oldPage.locator('#occ-read').textContent();

// -- new front: full shell + callboard + every tab --
const page = await browser.newPage({viewport: {width: 1700, height: 1000}});
page.on('pageerror', e => errors.push('NEW PAGEERROR: ' + e.message));
await page.goto('http://127.0.0.1:7901/static/booth/index.html', {waitUntil: 'networkidle'});
await page.waitForTimeout(1200);
await page.screenshot({path: OUT + '/new-shell.png'});
const newBoard = await page.locator('#callboard').boundingBox();
await page.screenshot({path: OUT + '/new-callboard.png', clip: newBoard});
const newStates = await page.locator('.station').evaluateAll(
    els => els.map(el => `${el.dataset.station}=${el.className.replace('station ', '')}`));
const newOcc = await page.locator('#occ-read').textContent();

console.log('old stations:', oldStates.join(' '));
console.log('new stations:', newStates.join(' '));
console.log('old occ:', oldOcc.trim(), '| new occ:', newOcc.trim());
console.log('states match:', JSON.stringify(oldStates) === JSON.stringify(newStates));

// every tab navigable
const tabs = await page.locator('nav [role=tab]').evaluateAll(els => els.map(el => el.dataset.tab));
console.log('tabs (' + tabs.length + '):', tabs.join(' '));
for (const t of tabs) {
    await page.locator(`nav [data-tab=${t}]`).click();
    await page.waitForTimeout(120);
    const visible = await page.locator(`#tab-${t}`).isVisible();
    const others = await page.locator('main > section:visible').count();
    if (!visible || others !== 1) errors.push(`TAB ${t}: visible=${visible} sections-visible=${others}`);
}
await page.locator('nav [data-tab=kiln]').click();
await page.waitForTimeout(150);
await page.screenshot({path: OUT + '/new-tab-kiln.png'});

console.log(errors.length ? errors.join('\n') : 'NO RUNTIME ERRORS');
await browser.close();
