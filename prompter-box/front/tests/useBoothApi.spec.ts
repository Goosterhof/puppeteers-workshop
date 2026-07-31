import {afterEach, describe, expect, it, vi} from 'vitest';
import {api} from '../src/composables/useBoothApi';

// The booth refuses POSTs that are not marked application/json — an unmarked
// one is a CORS simple request any other tab could have fired without a
// preflight. If this header is ever dropped, every cue starts 415ing.

type BoothFetch = (input: string, init?: RequestInit) => Promise<unknown>;

const reply = (body: unknown, ok = true) => ({
    ok,
    statusText: ok ? 'OK' : 'Bad Request',
    json: () => Promise.resolve(body),
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('the booth API voice', () => {
    it('marks every cue sheet application/json', async () => {
        const fetchSpy = vi.fn<BoothFetch>().mockResolvedValue(reply({state: 'running'}));
        vi.stubGlobal('fetch', fetchSpy);

        await api('/api/kiln/generate', {subject: 'a lantern'});

        const init = fetchSpy.mock.calls[0]![1]!;
        expect(init.method).toBe('POST');
        expect(init.headers).toStrictEqual({'Content-Type': 'application/json'});
        expect(init.body).toBe('{"subject":"a lantern"}');
    });

    it('a bodiless read stays a plain GET with no init at all', async () => {
        const fetchSpy = vi.fn<BoothFetch>().mockResolvedValue(reply({props: []}));
        vi.stubGlobal('fetch', fetchSpy);

        await api('/api/shelf/list');

        expect(fetchSpy.mock.calls[0]![1]).toBeUndefined();
    });

    it("speaks the booth's refusal, not the status line, when the door says no", async () => {
        vi.stubGlobal('fetch', vi.fn<BoothFetch>().mockResolvedValue(
            reply({error: 'The booth takes cue sheets marked application/json.'}, false),
        ));

        await expect(api('/api/rack/discard', {candidate_id: 'x'}))
            .rejects.toThrow('The booth takes cue sheets marked application/json.');
    });
});
