// The booth's API voice — the single place errors are shaped (#00063 §1A).
// Same contract as the single-file front: POST when a body is given, JSON
// either way, and an unreadable reply speaks in the booth's voice instead of
// a parser stack.
//
// `T` defaults to unknown on purpose: a fire-and-forget cue needs no
// annotation, but the moment a caller reaches into the reply it must say
// what it expects — that call-site contract is the whole point of the types.
// The Content-Type is load-bearing, not decoration: the booth refuses POSTs
// that are not marked application/json, because an unmarked one is a CORS
// simple request any other tab could have fired without a preflight.
export async function api<T = unknown>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(path, body
        ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}
        : undefined);
    const data = await res.json().catch(() => ({error: 'The booth lost the line — unreadable reply.'})) as T & {error?: string};
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
}
