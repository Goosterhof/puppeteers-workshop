import {mount} from '@vue/test-utils';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import App from '../src/App.vue';
import {activeTab} from '../src/stores/booth';

// The Prompt Book shell (#00064): four wings of thumb-tabs down the binder,
// one dog-eared into the lit folio page, and — since enhancement report
// #00009 (P2-6) — a complete ARIA tab pattern the keyboard can walk.

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn<(path: string, body?: unknown) => Promise<unknown>>()}));
vi.mock('../src/composables/useBoothApi', () => ({api: apiMock}));

// Rail order is the binder's own order, top to bottom — deliberately NOT the
// tab-definition order, which still opens on the Kiln second.
const RAIL = ['forge', 'face', 'stage', 'foley', 'kiln', 'rack', 'shelf', 'nightshift',
    'archive', 'house-stage', 'house-face'];

// shallow: the eleven rooms are stubbed — this spec is about the binder, and
// each room already answers for itself.
const openTheBook = () => mount(App, {shallow: true, attachTo: document.body});
const tabs = (w: ReturnType<typeof openTheBook>) => w.findAll('.rail .tab');
const tabFor = (w: ReturnType<typeof openTheBook>, id: string) => w.get(`[data-tab="${id}"]`);

describe('App — the Prompt Book shell', () => {
    beforeEach(() => {
        apiMock.mockReset();
        apiMock.mockResolvedValue({images: []});
        activeTab.value = 'forge';
    });

    it('the eleven lines hang in four named wings, in rail order', () => {
        const w = openTheBook();
        expect(w.findAll('.wing-head').map(h => h.text()))
            .toStrictEqual(['Performance', 'The Kiln Wing', 'The Vault', 'Understage']);
        expect(tabs(w).map(t => t.attributes('data-tab'))).toStrictEqual(RAIL);
        // a tablist may own only tabs, so the wings hand their names over by description
        expect(tabFor(w, 'forge').attributes('aria-describedby'))
            .toBe(w.get('.wing-head').attributes('id'));
        w.unmount();
    });

    it('one tab dog-ears at a time, and the running head names the open room', async () => {
        const w = openTheBook();
        expect(w.get('.runhead .folio b').text()).toBe('Forge');
        expect(tabs(w).filter(t => t.attributes('aria-selected') === 'true')).toHaveLength(1);

        await tabFor(w, 'archive').trigger('click');
        expect(w.get('.runhead .folio b').text()).toBe('The Canisters');
        expect(tabFor(w, 'archive').attributes('aria-selected')).toBe('true');
        expect(tabFor(w, 'forge').attributes('aria-selected')).toBe('false');
        w.unmount();
    });

    it('every tab controls a panel, and every panel names its tab back', () => {
        const w = openTheBook();
        const panels = w.findAll('[role="tabpanel"]');
        expect(panels).toHaveLength(RAIL.length);
        for (const id of RAIL) {
            const tab = tabFor(w, id);
            const panel = w.get(`#panel-${id}`);
            expect(tab.attributes('id')).toBe(`tab-${id}`);
            expect(tab.attributes('aria-controls')).toBe(`panel-${id}`);
            expect(panel.attributes('aria-labelledby')).toBe(`tab-${id}`);
        }
        w.unmount();
    });

    it('the rail holds ONE tab stop — the roving tabindex travels with the selection', async () => {
        const w = openTheBook();
        const stops = () => tabs(w).filter(t => t.attributes('tabindex') === '0');
        expect(stops()).toHaveLength(1);
        expect(stops()[0]!.attributes('data-tab')).toBe('forge');

        await tabFor(w, 'shelf').trigger('click');
        expect(stops()).toHaveLength(1);
        expect(stops()[0]!.attributes('data-tab')).toBe('shelf');
        expect(tabFor(w, 'forge').attributes('tabindex')).toBe('-1');
        w.unmount();
    });

    it('the arrows walk the RAIL, not the tab order, and wrap at both ends', async () => {
        const w = openTheBook();
        // Forge sits above Face Shop in the binder even though the Kiln is
        // defined second — the arrows follow the page, not the array.
        await tabFor(w, 'forge').trigger('keydown', {key: 'ArrowDown'});
        expect(activeTab.value).toBe('face');
        await tabFor(w, 'face').trigger('keydown', {key: 'ArrowUp'});
        expect(activeTab.value).toBe('forge');

        await tabFor(w, 'forge').trigger('keydown', {key: 'ArrowUp'});
        expect(activeTab.value).toBe('house-face'); // wraps to the foot of the rail
        await tabFor(w, 'house-face').trigger('keydown', {key: 'ArrowDown'});
        expect(activeTab.value).toBe('forge');

        // the rail is vertical, but a reader arriving sideways is not turned away
        await tabFor(w, 'forge').trigger('keydown', {key: 'ArrowRight'});
        expect(activeTab.value).toBe('face');
        await tabFor(w, 'face').trigger('keydown', {key: 'ArrowLeft'});
        expect(activeTab.value).toBe('forge');
        w.unmount();
    });

    it('Home and End jump to the ends, and the arrow carries focus with it', async () => {
        const w = openTheBook();
        await tabFor(w, 'forge').trigger('keydown', {key: 'End'});
        expect(activeTab.value).toBe('house-face');
        expect(document.activeElement).toBe(tabFor(w, 'house-face').element);

        await tabFor(w, 'house-face').trigger('keydown', {key: 'Home'});
        expect(activeTab.value).toBe('forge');
        expect(document.activeElement).toBe(tabFor(w, 'forge').element);
        w.unmount();
    });

    it('a key the pattern does not own is left to the browser', async () => {
        const w = openTheBook();
        const escape = new KeyboardEvent('keydown', {key: 'Escape', cancelable: true, bubbles: true});
        tabFor(w, 'forge').element.dispatchEvent(escape);
        expect(escape.defaultPrevented).toBe(false);
        expect(activeTab.value).toBe('forge');
        w.unmount();
    });
});
