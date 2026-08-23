import {mount} from '@vue/test-utils';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import ThumbRow from '../src/components/ThumbRow.vue';
import {footage} from '../src/stores/booth';

// The shelf's hatch (bring-your-own-still, 2026-08-23): a file through the
// hatch or dropped on the strip is shelved through the upload window, the
// shelf is re-read, and the new still is picked on arrival.

const {apiMock} = vi.hoisted(() => ({apiMock: vi.fn<(path: string, body?: unknown) => Promise<unknown>>()}));
vi.mock('../src/composables/useBoothApi', () => ({api: apiMock}));

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 9, 9]);
const still = (name = 'sitter.png', type = 'image/png') => new File([PNG], name, {type});

function routes(shelvedAs = 'sitter.png') {
    return (path: string): Promise<unknown> => {
        if (path === '/api/footage') return Promise.resolve({images: footage.value.includes(shelvedAs) ? footage.value : [...footage.value, shelvedAs]});
        if (path === '/api/footage/upload') return Promise.resolve({shelved: shelvedAs, bytes: PNG.length});
        return Promise.reject(new Error(`no window: ${path}`));
    };
}

const settle = async () => {
    for (let i = 0; i < 6; i++) await Promise.resolve();
};

describe('ThumbRow', () => {
    beforeEach(() => {
        apiMock.mockReset();
        apiMock.mockImplementation(routes());
        footage.value = ['crier.png'];
    });
    afterEach(() => {
        footage.value = [];
    });

    it('shows the hatch at the head of the strip, before the footage', () => {
        const wrapper = mount(ThumbRow);
        const first = wrapper.element.children[0] as HTMLElement | undefined;
        expect(first?.tagName.toLowerCase()).toBe('button');
        expect(first?.classList.contains('hatch')).toBe(true);
        expect(wrapper.findAll('img')).toHaveLength(1);
        expect(wrapper.find('input[type="file"]').attributes('accept')).toBe('image/png,image/jpeg,image/webp');
        wrapper.unmount();
    });

    it('a file through the hatch is shelved as base64, the shelf re-read, and the arrival picked', async () => {
        const wrapper = mount(ThumbRow);
        const input = wrapper.find<HTMLInputElement>('input[type="file"]');
        Object.defineProperty(input.element, 'files', {value: [still()], configurable: true});
        await input.trigger('change');
        await settle();

        expect(apiMock).toHaveBeenCalledWith('/api/footage/upload', {name: 'sitter.png', data: btoa(String.fromCharCode(...PNG))});
        expect(apiMock).toHaveBeenCalledWith('/api/footage');
        expect(footage.value).toContain('sitter.png');
        expect(wrapper.emitted('pick')).toStrictEqual([['sitter.png']]);
        wrapper.unmount();
    });

    it('picks the name the SHELF gave it, not the name the browser claimed', async () => {
        apiMock.mockImplementation(routes('crier-2.png'));
        const wrapper = mount(ThumbRow);
        const input = wrapper.find<HTMLInputElement>('input[type="file"]');
        Object.defineProperty(input.element, 'files', {value: [still('crier.png')], configurable: true});
        await input.trigger('change');
        await settle();
        expect(wrapper.emitted('pick')).toStrictEqual([['crier-2.png']]);
        wrapper.unmount();
    });

    it('a drop anywhere on the strip goes through the same door', async () => {
        const wrapper = mount(ThumbRow);
        await wrapper.trigger('dragover');
        expect(wrapper.classes()).toContain('hovering');
        await wrapper.trigger('drop', {dataTransfer: {files: [still('dropped.png')]}});
        await settle();
        expect(wrapper.classes()).not.toContain('hovering');
        expect(apiMock).toHaveBeenCalledWith('/api/footage/upload', expect.objectContaining({name: 'dropped.png'}));
        expect(wrapper.emitted('pick')).toHaveLength(1);
        wrapper.unmount();
    });

    it('a dropped video is refused at the strip, in the shelf\'s voice, without knocking', async () => {
        const wrapper = mount(ThumbRow);
        await wrapper.trigger('drop', {dataTransfer: {files: [new File([PNG], 'take.mp4', {type: 'video/mp4'})]}});
        await settle();
        expect(apiMock).not.toHaveBeenCalledWith('/api/footage/upload', expect.anything());
        expect(wrapper.find('.refusal').text()).toContain('PNG, JPEG, or WebP');
        expect(wrapper.emitted('pick')).toBeUndefined();
        wrapper.unmount();
    });

    it('the booth\'s refusal is shown on the strip and nothing is picked', async () => {
        apiMock.mockImplementation((path: string) => path === '/api/footage/upload'
            ? Promise.reject(new Error('The shelf takes stills only — that file opened as something else.'))
            : Promise.resolve({images: footage.value}));
        const wrapper = mount(ThumbRow);
        await wrapper.trigger('drop', {dataTransfer: {files: [still('lying.png')]}});
        await settle();
        expect(wrapper.find('.refusal').text()).toContain('opened as something else');
        expect(wrapper.emitted('pick')).toBeUndefined();
        expect(wrapper.find('.hatch').attributes('disabled')).toBeUndefined();
        wrapper.unmount();
    });

    it('clicking a still on the strip still picks it — the hatch changed nothing there', async () => {
        const wrapper = mount(ThumbRow, {props: {picked: null}});
        await wrapper.find('img[title="crier.png"]').trigger('click');
        expect(wrapper.emitted('pick')).toStrictEqual([['crier.png']]);
        wrapper.unmount();
    });
});
