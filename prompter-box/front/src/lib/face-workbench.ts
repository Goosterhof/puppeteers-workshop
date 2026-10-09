export interface StillAsset {room: 'footage' | 'face' | 'stage'; name: string}
export interface FaceRecipe {prompt: string; seed: number; model: string; width: number; height: number; source: string | null}
export interface FaceRevision {name: string; recipe: FaceRecipe; source: StillAsset | null}
export interface FaceWorkbench {
    original: StillAsset | null;
    revisions: FaceRevision[];
    selected: string | null;
    draft: {prompt: string; source: string | null; width: number; height: number; seed: number; model: string; keep?: string};
    pending: {id: string; recipe: FaceRecipe; source: StillAsset | null} | null;
}
const KEY = 'workshop-face-workbench-v1';
export const stillUrl = (a: StillAsset) => `${a.room === 'footage' ? '/footage/' : `/${a.room}-output/`}${encodeURIComponent(a.name)}`;
const asset = (a: unknown): a is StillAsset => !!a && typeof a === 'object'
    && ['footage', 'face', 'stage'].includes(String((a as StillAsset).room)) && typeof (a as StillAsset).name === 'string';
const recipe = (r: unknown): r is FaceRecipe => !!r && typeof r === 'object'
    && typeof (r as FaceRecipe).prompt === 'string' && typeof (r as FaceRecipe).model === 'string'
    && ['seed', 'width', 'height'].every(k => Number.isFinite((r as unknown as Record<string, number>)[k]))
    && ((r as FaceRecipe).source === null || typeof (r as FaceRecipe).source === 'string');

const revision = (r: FaceRevision) => !!r && typeof r.name === 'string' && recipe(r.recipe)
    && (r.source === null || asset(r.source));
const pending = (p: FaceWorkbench['pending']) => p === null || (!!p && typeof p.id === 'string' && recipe(p.recipe)
    && (p.source === null || asset(p.source)));
const validDraft = (d: FaceWorkbench['draft']) => recipe(d) && (d.keep === undefined || typeof d.keep === 'string');
function workbench(w: FaceWorkbench): boolean {
    return !!w && Array.isArray(w.revisions) && validDraft(w.draft)
        && (w.original === null || asset(w.original)) && (w.selected === null || typeof w.selected === 'string')
        && pending(w.pending);
}
export function readFaceWorkbench(): FaceWorkbench | null {
    try {
        const w = JSON.parse(localStorage.getItem(KEY) || 'null') as FaceWorkbench;
        return workbench(w) ? {...w, revisions: w.revisions.filter(revision).slice(-40)} : null;
    } catch { return null; }
}

export function saveFaceWorkbench(w: FaceWorkbench): void {
    try { localStorage.setItem(KEY, JSON.stringify({...w, revisions: w.revisions.slice(-40)})); }
    catch { /* A private browser can refuse persistence; the live bench still works. */ }
}
