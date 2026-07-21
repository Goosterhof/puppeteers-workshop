// The booth's API voice — the single place errors are shaped (#00063 §1A).
// Same contract as the single-file front: POST when a body is given, JSON
// either way, and an unreadable reply speaks in the booth's voice instead of
// a parser stack.
export async function api(path, body) {
    const res = await fetch(path, body ? {method: 'POST', body: JSON.stringify(body)} : undefined);
    const data = await res.json().catch(() => ({error: 'The booth lost the line — unreadable reply.'}));
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
}
