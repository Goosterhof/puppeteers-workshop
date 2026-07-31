# The Puppeteer's Workshop — Gadget Lab Journal

The laboratory's local AI **video pipeline**: motion transfer, character swap,
voice cloning, and the instruments the Mad Scientist built around them. This is
the workshop that animated the town crier's bell (the protectorate's 193 KB
VP9 WebM) and where every future lab video asset gets made.

**Read [`runbook.md`](runbook.md) before touching anything** — it is the
operating manual: the pipeline map, model inventory, hard-won constraints, and
the incident write-ups (including the double WSL VM death of 2026-07-09 that
shaped the VRAM choreography).

## The blueprint / workshop-floor split

This repo tracks only the instruments (~100 KB). The machines they operate are
installed on the workshop floor and are **never tracked**:

| On the floor (gitignored) | What it is |
|---|---|
| `Wan2GP/` (~93 GB) | deepbeepmeep/Wan2GP clone + venv + Wan 2.2 / SCAIL-2 / OmniVoice weights |
| `ComfyUI/` (~30 GB) | ComfyUI clone + venv + Flux 2 Klein 9B GGUF stack |
| `MMAudio/` (~10 GB) | hkchengrex/MMAudio clone + venv — **the Foley Booth**: text-to-audio + video-synchronized audio (weights CC-BY-NC, internal tooling only — see runbook) |
| `ffmpeg-shared/` | BtbN FFmpeg 7.1 shared libs — torchcodec's substrate (sudo-free) |
| `footage/` | personal media — start images, driving video, casting archive |

**The canonical working bench is `~/code/video-lab`** — the only checkout with
the machines installed. The lab's submodule at `gadgets/puppeteers-workshop`
is the blueprint copy for the manifest; do the work on the bench, push, then
bump the lab's ref (submodule discipline).

## The instruments

| Instrument | Location | What it does |
|---|---|---|
| **The Prompter's Box** | `prompter-box/` (`./start-prompter.sh` → :7900) | The unified console — forge cues (voice pick from the Ollama shelf), paint in the Face Shop (headless ComfyUI, painter pick from the storeroom), animate on the Stage (headless `wgp.py --process` with a performer playbill enumerated from the weights on the floor — i2v 14B, t2v 5B, SCAIL-2 motion transfer, Krea 2 stills — each with a LoRA wardrobe off its family shelf plus steps/guidance knobs), score in the Foley Booth (headless MMAudio t2a/v2a — a Stage take is one click from its soundtrack), cast paintings into footage, all with fail-closed VRAM choreography. **The front is the Proscenium** (#00063, 2026-07-21): a Vue 3 + UnoCSS + Vite **TypeScript** app in `prompter-box/front/` (TS crossing 2026-07-22 at the investor's cue — strict `vue-tsc`, Mezzanine-grade tsconfig; supersedes #00063 §1A's plain-JS-by-design, a port-parity choice now spent) that builds into `prompter-box/static/` (committed bundle — the bench pulls, never builds); `server.py` stays stdlib and never noticed. **The layout is the Prompt Book** (#00064, 2026-07-22, investor-ruled from a 3-variant Artisan/Illusionist audition in `front/auditions/`): the active room performs on a lit folio page (the `.folio-page` scope remaps the semantic aliases so rooms invert to ink-on-paper with zero room-file edits — the `--ui-*` atom map is re-declared there because var()s in custom properties bake at `:root`), the eleven rooms hang as ring-binder thumb-tabs in four wings down the stage-right rail (the active tab dog-ears into the page), and the Callboard types itself as the footlight ledger along the bottom lip — LIVE by value, no pulse, same heartbeat and evict contract. Log wells stay dark: tipped-in photographs on the folio. Front containment: `cd prompter-box/front && npm run lint && npm run typecheck && npx vitest run && npm run check:dist` (drift guard: a stale committed bundle fails; `npm run build` type-checks before it bundles). Never edit `static/` by hand — `vite build` empties it |
| **The Promptsmith** | `prompt-forge/promptsmith.py` | Generation-prompt forge on local Ollama models — `qwen3:14b` text, `qwen3-vl:8b` with `--image` (reads the stillness inventory off the actual pixels) |
| **The Framewright** | `crop-tool/croptool.py` | Exact-resolution cropper with Wan presets — resolution discipline is the whole game in motion transfer |
| **The Keymaster** | `prompter-box/keymaster.py` | Topology-aware background keying for illustrated takes — only border-connected regions (or `--min-island` pockets) are keyed, so a scroll face can never be eaten the way plain colorkey ate the TC-0057 wax seals; outputs multiply-ready VP9 WebM. The one instrument excused from the stdlib rule (numpy + Pillow + scipy — run it with a machine venv's python; see the runbook) |
| **The Kiln Room** | `prompter-box/kiln.py` + `turntable.py` + `night_shift.py` + `stagehands.py` | The prop-firing spine (experiment log #00062): a subject phrase becomes a keyed, despilled, +6px-cropped hide and a Hunyuan3D GLB in one chain, with the Turntable's silhouette/voxel/island checks catching shredded thin structures and auto-refiring once at 224/0.4; every firing parks `pending` on the **Curing Rack** (nothing reaches `pack-queue/` without a thumb on Approve) and the **Night Shift** works a persisted call sheet overnight through the SAME `clear_the_set` guard (`stagehands.py` — the guard family extracted from server.py, one definition for every station). qwen3-vl grounds each firing and writes its Canister label. Turntable renders headless via pyrender+EGL; the shared guard rule stands unweakened. Containment: `python -m pytest prompter-box/tests/` (fixture-driven, no GPU; run with the ComfyUI venv python — see `prompter-box/requirements.txt`). Bench graft landed 2026-07-19 and the live end-to-end gate is witnessed: the omafiets shredded at 128, auto-refired to a QA-passing 224/0.4 mesh, cleared the real `pack-props.mjs` round-trip, and a 3-row Night Shift (one K=2) parked 4 labeled candidates unattended. Verify server changes live via `verify-sideport.py` on :7901 — never the investor's :7900 booth. Every candidate mounts on the **Potter's Wheel** (`front/src/lib/potters-wheel.ts`, wrapped by `PottersWheel.vue`) — a live drag-to-orbit GLB viewer, lit by a camera-riding over-the-shoulder key so no angle is ever dark: the firing bench mounts fresh pieces directly; on the Rack a click spotlights ONE candidate in an enlarged Canisters-style card above the grid (only the piece on the wheel turns — the shelf keeps a slow 4-second strip turn), and the whole booth runs one wide 1680px column on large monitors (every tab, one width). Kiln settings carry knob-notes (octree = carving grid, threshold = voxel skin cut, seed = paint+mesh dice). Approved pairs surface in-booth on **the Prop Shelf** (`/api/shelf/list` reads pack-queue/ back as the Workshop's own prop library, married to each firing's record — consumers like the town sketches' `pack-props.mjs` come to the shelf, not the reverse), and the Rack carries a third verdict: **Discard** breaks a pending firing for good behind the break-pit confirm dialog (`rack_discard` — pending only, approved/superseded stay as the audit trail). three.js is an npm dep of the front (pinned 0.177, a lazy chunk — the vendor dir retired with the single-file era at the #00063 cutover). |

## Containment — the Sentinel, the lock on `main`, and how a change lands

The blueprint gates itself. **`.github/workflows/sentinel.yml`** (armed
2026-07-31, PR #5, after Librarian audit #00003 found the Workshop was the one
PUBLIC lab repo with no CI at all) runs on every push to `main` and every PR
against it, in two jobs:

| Job | What it guards | The gate set |
|---|---|---|
| **proscenium** | the front — `prompter-box/front/` (Vue 3 + strict TS) | `npm ci`, then `npm run lint` (oxlint), `npm run typecheck` (`vue-tsc --noEmit`), `npx vitest run`, `npm run check:dist` (rebuilds and fails on a stale committed `static/` bundle) |
| **kiln-room** | the Kiln Room's Python spine and the booth's HTTP layer | `pip install numpy pillow scipy trimesh pytest`, then `python -m pytest prompter-box/tests/` — fixture-driven, no GPU, pyrender deliberately absent (`turntable.py` lazy-imports it only on the real EGL path, which this suite never takes) |

**No job fires the machines.** A green Sentinel means the blueprint is sound,
not that the bench can perform — that stays the live-fire gate's job.

This repo is one of the four PUBLIC lab repos, so the 2026-06-16 Sentinel
quota freeze does not touch it: **these runs actually happen, and their red is
real.** Locally the same gates are `cd prompter-box/front && npm run lint &&
npm run typecheck && npx vitest run && npm run check:dist` and
`python -m pytest prompter-box/tests/` (ComfyUI venv python — see
`prompter-box/requirements.txt`).

### The merge path

**`main` is branch-PROTECTED (a direct push is refused with GH006).** A change
lands like this, and never any other way:

1. Branch in the checkout you are working from, off the `origin/main` tip —
   fetch and confirm first. The bench at `~/code/video-lab` and the lab's
   submodule copy drift apart; whichever one you cut from, verify ITS baseline.
2. Run every gate above locally. The Sentinel will run them again, but a red
   PR costs a round trip.
3. Push the branch and open a PR (`gh pr create --head <branch>`).
4. **The investor's merge is the authorization** — squash-merge, which mints a
   NEW commit SHA on `main`.
5. Because the SHA is new, the parent lab repo's gitlink is orphaned until it
   is re-pointed at the merged commit. Re-point it AFTER the merge, in the
   parent repo, as a `sync(workshop): ...` commit. `git status` in the parent
   looks clean while the gitlink is stale, so this step has to be deliberate.

When a session changes **what** gates this repo, this section is part of that
change — not follow-up. The journal turns with the gates.

## Conventions

- Stdlib-only Python for the instruments — no venvs of our own; the machines
  carry their own. (The Keymaster is the standing exception: its topology maths
  need numpy + Pillow + scipy, borrowed from a machine venv's python. The Kiln
  Room extends the same exception: `kiln.py`/`turntable.py` add trimesh +
  pyrender for mesh QA — declared in `prompter-box/requirements.txt`, installed
  into the ComfyUI venv, run with that venv's python.) The Proscenium keeps the
  rule at RUNTIME: Node/npm in `prompter-box/front/` are development-time only —
  the committed `static/` bundle is what the stdlib server serves; the bench
  pulls, never builds.
- Commit scope: `workshop` (see the lab's Commit Doctrine).
- Gadget containment protocols apply: the Prompter's Box carries the
  `prefers-reduced-motion` floor in its single-page CSS.
- The GPU is a one-performance stage: anything that loads a model goes through
  the Prompter's Box guard (`clear_the_set()`) or checks `nvidia-smi` first.
  Never weaken the guard to best-effort — see runbook §The Stagehands' Guard.
