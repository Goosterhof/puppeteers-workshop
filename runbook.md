# The Puppeteer's Workshop — local AI video pipeline

> Successor wing to `~/code/local-llm-spike/` (LLM spike, parked). This wing is the
> **video** pipeline from the reference video (SCAIL-2 motion transfer + character swap
> + voice cloning), running locally on the RTX 5090 (32 GB VRAM) under WSL2.
> Set up 2026-07-03.

## The pipeline → local tool map

| # | Video step | Local tool | Status |
|---|-----------|-----------|--------|
| 1 | Motion transfer (SCAIL-2) | **Wan2GP** — SCAIL-2 model, auto-downloads on first select | installed |
| 2 | Character swap (Flux 2 Klein) | **ComfyUI** + Klein 9B GGUF + ComfyUI-GGUF node | installed |
| 3 | Custom crop tool | `crop-tool/` — ours, ffmpeg-based | planned |
| 4 | SCAIL-2 replacement (mask/feather/blend) | Wan2GP SCAIL-2 replacement mode | with #1 |
| 5 | Final composite | CapCut on Windows (user-side; exchange files via `/mnt/c`) | n/a |
| 6 | Voice cloning (OmniVoice) | Wan2GP — OmniVoice TTS (zero-shot clone from short clip) | with #1 |
| 7 | Relay Prompt | Wan2GP — LTX2 time-ranged prompts: `[25%:50%] the character says "…"` | with #1 |
| 8 | Omni LoRA (a/v sync) | Wan2GP — LTX2 OmniNFT LoRA preset | with #1 |
| 9 | Sound effects + foley (T2A / V2A) | **MMAudio** — text-to-audio and video-synchronized audio | installed (2026-07-11) |

## Layout

```
video-lab/
├── Wan2GP/            # deepbeepmeep/Wan2GP, .venv python 3.11, torch 2.10 cu130
├── ComfyUI/           # comfyanonymous/ComfyUI, .venv python 3.12, torch cu130
│   ├── custom_nodes/ComfyUI-GGUF/     # loads the Klein GGUF quants
│   └── models/{diffusion_models,text_encoders,vae}/
├── crop-tool/         # step 3 — exact-resolution cropper (to build)
├── MMAudio/           # hkchengrex/MMAudio, .venv python 3.11, torch 2.13 cu130 — the Foley Booth
├── ffmpeg-shared/     # BtbN FFmpeg 7.1 SHARED build — torchcodec's substrate (see The Foley Booth)
├── start-wangp.sh     # → http://localhost:7860
└── start-comfyui.sh   # → http://localhost:8188
```

## Models

| File | Where | Source | Note |
|------|-------|--------|------|
| `flux-2-klein-9b-BF16.gguf` | `ComfyUI/models/diffusion_models/` | `unsloth/FLUX.2-klein-9B-GGUF` | ungated; full precision, ~18 GB — fits the 5090 |
| `qwen_3_8b_fp8mixed.safetensors` | `ComfyUI/models/text_encoders/` | `Comfy-Org/flux2-klein-9B` | ungated |
| `flux2-vae.safetensors` | `ComfyUI/models/vae/` | `Comfy-Org/flux2-dev` | ungated |
| `hunyuan_3d_v2.1.safetensors` | `ComfyUI/models/checkpoints/` | `Comfy-Org/hunyuan3D_2.1_repackaged` | ungated; 7.4 GB all-in-one (DiT + CLIP-vision + VAE). **The latent kiln** — image→GLB mesh via ComfyUI-native nodes (`ImageOnlyCheckpointLoader → CLIPVisionEncode → Hunyuan3Dv2Conditioning → KSampler 30 steps cfg 5 → VAEDecodeHunyuan3D → VoxelToMesh "surface net" → SaveGLB`); ~30 s per mesh on the 5090. Shape only — no texture stage in core ComfyUI; planar-project the source painting in the consumer (edge-pad the keyed texture first, seeding from interior colors so the outline ring never smears). **Web-prop firing settings (2026-07-11, De Wandeling):** `octree_resolution: 128` keeps a prop under 3 MB (default 256 → ~11 MB surface-net mesh), silhouette fine at walking distance; refiring the same LoadImage + seed hits the cached KSampler latent — decode+mesh only, seconds not 30, so octree/threshold iteration is nearly free. Prompt-side: keep the chroma-key color disjoint from the subject's palette ("bronze with green patina" poisoned a green screen — magenta rescued it), and removing an iconic part fails as negation at cfg=1 — strong positive story phrasing ("sails dismounted and taken away for restoration") works on every seed. Kiln meshes bake y-up: trust it — axis-guessing laid a monument on its side. First firing: the Menagerie's Carousel Figure (2026-07-10) |
| SCAIL-2 / OmniVoice / LTX2 | Wan2GP manages | auto-download on first use | pick in the Wan2GP UI |

**Gated upgrade path:** the official `black-forest-labs/FLUX.2-klein-9b-fp8` safetensors
are `gated: auto` on HuggingFace — log in, click agree, mint a read token, put it in
`~/.cache/huggingface/token`, then the fp8 files download fine and the GGUF node becomes
optional. Not required — BF16 GGUF is already ≥ fp8 quality.

**Character-swap extras spotted on HF (untested):** `nhathoangfoto/Flux.2-Klein-9B-SmartCharacterSwap`,
`thedeoxen/refcontrol-FLUX.2-klein-9B-reference-pose-lora`, `dx8152/Flux2-Klein-9B-Consistency`.

## The Foley Booth — MMAudio (added 2026-07-11)

Text-to-audio AND video-to-audio (flow-matching, CVPR 2025). The V2A half watches
the frames through a sync module, so a silent take comes back with its sound
landing on the motion — the crier's bell swing was its first customer. ~6 GB VRAM
in 16-bit; `large_44k_v2` weights auto-download ungated from HF on first run.

**License posture:** code MIT, weights **CC-BY-NC 4.0**. The investor accepted the
non-commercial weights for internal tooling (2026-07-11) — fine for lab benches and
internal consoles; anything outward-facing or sold regenerates its audio with a
commercially-clear tool.

**Bolting it down from scratch:**

```bash
cd ~/code/video-lab && git clone https://github.com/hkchengrex/MMAudio.git
cd MMAudio && uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python torch torchaudio torchvision \
  --index-url https://download.pytorch.org/whl/cu130
uv pip install --python .venv/bin/python -e .
# torchcodec needs FFmpeg SHARED libs (libavutil.so.*) — the static binaries in
# ~/.local/bin carry none, and there is no sudo. The cure: BtbN's shared build.
mkdir -p ../ffmpeg-shared && curl -sL -o /tmp/ff.tar.xz \
  "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-linux64-gpl-shared-7.1.tar.xz"
tar -xf /tmp/ff.tar.xz --strip-components=1 -C ../ffmpeg-shared
```

**Running takes** (always with the substrate on the path):

```bash
export LD_LIBRARY_PATH="$HOME/code/video-lab/ffmpeg-shared/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
.venv/bin/python demo.py --duration=8 --seed 7 --negative_prompt "music" \
  --prompt "a man screams in terror" --output output/screams           # T2A
.venv/bin/python demo.py --seed 7 --video <take.mp4> \
  --prompt "a small brass hand bell rings brightly" --output output/takes  # V2A
```

Hard-won on day one:
- **Output filename = prompt slug** — two seeds of the SAME prompt into the same
  `--output` dir silently overwrite each other. Per-run output dirs or rename
  between runs.
- V2A snaps duration to the clip; T2A holds best at the trained 8 s — generate
  long, trim the sting with ffmpeg.
- Negative-prompt `"music, background music, melody"` — the README's own warning
  about unsolicited scoring, confirmed worth pinning.
- GPU discipline unchanged: check `nvidia-smi` / `ollama ps` before a run like
  every other machine on the floor (~6 GB ask, coexists with more than the
  diffusion stacks do, but the one-performance rule stands).

## The Prompt Forge — local LLMs (added 2026-07-09)

Two local models on the existing Ollama daemon (`localhost:11434`) serve the
workshop's development loop. This reopens the LLM wing that was parked in
`~/code/local-llm-spike/` — but only the part that was **proven working** there:
plain chat with slim prompts. The parked verdict stands for the other part —
do NOT retry wiring a sub-32B model into an agentic Claude-Code-style harness.

| Model | Size | Role |
|-------|------|------|
| `qwen3:14b` | ~9.3 GB | **The Promptsmith's anvil** — generation-prompt drafting for Wan2GP / ComfyUI |
| `qwen3-vl:8b` | ~6.1 GB | **The Promptsmith's eyes** — vision-grounded forging: pass `--image <start image>` (CLI) or pick a lead on the Forge tab and the stillness inventory is read off the actual pixels instead of typed by hand |
| `qwen3-coder:30b-a3b-q4_K_M` | ~18 GB | Coding chat — quick scripts, ffmpeg incantations, workflow JSON surgery |

**Forging prompts** — `prompt-forge/promptsmith.py` bakes the workshop's
hard-won prompt rules into per-target system prompts:

```bash
prompt-forge/promptsmith.py wan   "the crier swings his bell twice, cloak sways"
prompt-forge/promptsmith.py flux  "pirate captain portrait, warm rim light"
prompt-forge/promptsmith.py relay "mascot greets the viewer, then rings the bell"
```

Targets: `wan` (i2v motion-first, never redescribes the start-image character —
made an EXPLICIT never-name-the-species clause 2026-08-02 after both forged
variants for a triceratops walk cue invented taxonomy, "sauropod" and
"theropod", which risks morphing the i2v character), `flux` (Klein 9B
single-paragraph, positive-only), `relay` (LTX2 time-ranged segments). All
three enforce the cfg=1 lesson: distilled models ignore negative prompts, so
everything is phrased as what you WANT.

**Coding chat** — `ollama run qwen3-coder:30b-a3b-q4_K_M` for an interactive
session, or point any OpenAI-compatible client at `localhost:11434/v1`.

## The Prompter's Box — the unified console (added 2026-07-09)

`./start-prompter.sh` → **http://localhost:7900** — one booth for the whole
pipeline (stdlib Python, `prompter-box/`, no venv):

**The Proscenium (2026-07-21, experiment log #00063):** the booth front is a
Vue 3 + UnoCSS + Vite app in `prompter-box/front/`. `npm run build` (bench
Node v24 — a development-time tool only) emits the bundle into
`prompter-box/static/`, and the bundle is **committed**: the bench serves
straight after `git pull` with zero build steps, and the stdlib-runtime rule
stands — `server.py` never grew a dependency and keeps serving `static/` as
plain files (`/` → `static/index.html`, assets under `/static/`).
Front containment: `cd prompter-box/front && npm run lint && npm run
typecheck && npx vitest run && npm run check:dist` — the drift guard rebuilds
and fails the moment the committed bundle is stale against the source. Never
edit `static/` by hand; it is build output (`vite build` empties it). Verify
UI changes on the :7901 sideport (`verify-sideport.py`), never the investor's
:7900 booth. three.js rides as an npm dep (pinned 0.177, the old vendored
version) in a lazy chunk; the Potter's Wheel module lives at
`front/src/lib/potters-wheel.ts`.
The front is **TypeScript** (2026-07-22, investor's cue — supersedes
#00063 §1A's "plain JS by design", which was a port-parity choice for the
cutover): strict `vue-tsc` (Mezzanine-grade tsconfig, `noUncheckedIndexedAccess`
included) is the type gate, oxlint stays the style gate, and `npm run build`
type-checks before it bundles — a type error now fails the drift guard too.
The layout is **the Prompt Book** (#00064, 2026-07-22, ruled from the
3-variant audition in `front/auditions/` — spec + mocks committed there):
folio deck left (rooms invert to ink-on-paper via the `.folio-page`
alias remap — no room-file edits; the `--ui-*` map re-declares under the
scope because custom-property var()s bake at `:root`), binder rail right
(four wings, dog-eared active tab, overflow-visible on purpose — a scroll
container would clip the jut), typed footlight ledger along the bottom
(LIVE by value, no pulse; same heartbeat/evict contract). The window
never scrolls — the folio does.

- **Forge** — the Promptsmith in a panel: idea → cue cards, each with
  copy / "Cue the stage" / "Cue the face shop" buttons. A **voice dropdown**
  (2026-07-18) lists every model on the Ollama shelf; "the booth decides"
  keeps the house pairing (qwen3:14b text, qwen3-vl:8b when sighted).
- **The Stage** — headless Wan2GP runs (`wgp.py --process`) with a
  **performer dropdown** (added 2026-07-18): the playbill enumerates every
  Wan2GP model type whose weights are actually in `ckpts/` (matching the
  defaults JSONs' URL basenames — plus the LoRA check that keeps SVI 2 Pro
  off the bill until its LoRA lands). Per-performer recipes layer the model's
  `defaults/*.json` with the bench's own saved `settings/*_settings.json`,
  and the UI reshapes per kind: Enhanced Lightning 14B (i2v, the bell-swing
  arc house lead), TI2V 5B (t2v, lead optional, 12 GB guard), SCAIL-2 14B
  (motion transfer — lead is the character, plus a choreography dropdown of
  footage/Stage reels feeding `video_guide`), Krea 2 RAW (t2i on the Stage's
  boards — no frames, stills land with **"Cast as a lead →"** to feed them
  back into `footage/`). Settings JSONs land in `jobs/prompter-*.json`, logs
  in `jobs/logs/`. Drop new weights into `ckpts/` and they appear on the
  playbill without touching the booth. Each performer also carries a
  **LoRA wardrobe** (2026-07-18): the playbill lists the safetensors on
  that performer's shelf — dir mapping mirrors the family handlers
  (`i2v_2_2` family → `loras/wan`, 5B → `loras/wan_5B`, SCAIL-2 →
  `loras/wan_i2v`, Krea 2 → `loras/krea2`) — click to don, set a strength
  per garment (`activated_loras` + space-joined `loras_multipliers` in the
  settings JSON). **Steps** and **guidance** knobs prefill from each
  recipe and override per cue — accelerator LoRAs (FastWan) want few
  steps at guidance 1. Ratified 2026-07-18: 5B + FastWan, 8 steps @
  guidance 1, 41 frames 720p in 42.8 s. Per-cue settings JSONs
  (`jobs/prompter-*.json`) are take artifacts, gitignored.
- **Image → image, both rooms** (2026-07-18, both ratified live) — the
  Face Shop takes an optional **sitter**: with one picked the painter
  EDITS via the archive's own night-crier recipe (ReferenceLatent on
  both conditionings, source scaled to ~1 MP, output follows its dims;
  the booth copies the sitter into `ComfyUI/input/` because LoadImage
  only reads there). The Stage's image performers (Krea 2) take an
  optional lead + a **Strength** knob: Wan2GP img2img is `image_mode 2`
  + `video_prompt_type "VG"` + `image_guide` + `denoising_strength` +
  `model_mode 0`. Two traps, learned at ratification cost: the letter
  grammar honors `denoising_strength` only with **"G"** (plain "V"
  forces 1.0), and a settings JSON **without `settings_version`** is
  treated as ancient — `fix_settings` rewrites `video_prompt_type` to
  the model's inpaint default whose "A" then demands a mask. The booth
  stamps `settings_version: 2.66` on every cue.
- **The Canisters** (2026-07-18) — the dedicated archive tab. Every
  previous take, painting, and score served straight off the output dirs
  (`/api/archive`, newest first, 150 per room) as **labeled cards**: the
  booth reads each canister's embedded recipe — Wan2GP writes its full
  settings into the mp4 comment tag (`metadata_type: "metadata"` in
  `wgp_config.json`), ComfyUI embeds the API graph in PNG text chunks
  (full-UI paintings included), MMAudio's prompt is its filename slug.
  Cards show prompt, model, seed, steps, cfg, resolution, frames,
  duration, LoRAs worn, age, size — probed once per file (ffprobe /
  pure-python PNG chunk walk), cached by mtime. Filters: search (matches
  metadata too, so `fastwan` or a seed finds takes), room pills, kind
  pills. Mounting a canister shows the full cue with **"Copy the cue"**
  plus its pipeline actions — stage reels score in the foley booth,
  stage stills cast as leads, paintings send to the stage. Refreshes on
  tab entry and after every finished job. (Replaced the short-lived
  per-panel racks the same day — history lives in its own room.)
- **Face Shop** — headless text-to-image via the ComfyUI API (needs
  `./start-comfyui.sh` running); result renders inline in seconds. A
  **painter dropdown** (2026-07-18) enumerates `ComfyUI/models/
  diffusion_models/` (GGUF loads through `UnetLoaderGGUF`, safetensors
  through `UNETLoader`) — but the qwen3 text encoder and flux2 VAE are
  bolted to the easel, so only Flux 2 family painters pair. Klein 9B
  remains the house painter.
  Every painting carries **"Send to the stage →"**: copies it into `footage/`,
  jumps to the Stage with it preselected, and snaps the resolution to the
  nearest Wan aspect — paint the character, then animate it, one click apart.
- **Foley Booth** (added 2026-07-11) — headless MMAudio: a cue alone is
  text-to-audio (8 s sweet spot, trim the sting after); pick a reel from
  footage/ or the Stage's fresh takes and the sync module scores the frames
  (V2A, duration snaps to the clip). Every finished Stage take carries
  **"Score it in the foley booth →"** — animate, then sound, one click apart.
  Per-cue output dirs dodge the prompt-slug overwrite trap; the booth injects
  `LD_LIBRARY_PATH` for torchcodec's FFmpeg-shared substrate itself. Guarded
  at 8 GB via the same fail-closed stagehands; refused while the Stage or the
  full Wan UI performs.
- **VRAM choreography** — the callboard (2026-07-18, chaos #00084 det. 8) is
  the booth's dominant live object: four station plates (Forge / Face Shop /
  Stage / Foley) each with a lamp-eye — ready green, standby amber, LIVE
  filament (one sun at most, per the mutex), HELD cue-red when the full Wan2GP
  UI occupies :7860 (a held stage refuses every cue — red, never green) — plus
  a stage-load dimmer fed by the Face Shop's real VRAM numbers, falling back
  to driver truth (nvidia-smi, chaos #00085 det. 2) when ComfyUI is dark —
  the meter only reads "— no meter" when the driver itself is silent. The
  Face Shop plate goes LIVE on a running paint via a `/queue` probe (det. 1,
  booth-cued or full-UI alike). Every generation cue auto-evicts loaded LLMs first; "Clear the
  boards" is the master blackout — lamps cool L→R, the reply voiced on the
  button. While a take runs the page's header wash warms (`body.take-running`).
  Fresh results mount as stamped prints (the archive's canister DNA with a
  "Fresh" stamp instead of an age chip), and a mounted archive canister wears
  the SAME Print paper with its age where Fresh sits (chaos #00085 det. 3);
  design record in the lab's
  `documents/wireframes/00037-wire-prompter-box-callboard.md`.
- **The Stagehands' Guard (FAIL-CLOSED — incident 2026-07-09)** — before the
  forge loads an LLM (13 GB VRAM needed) or the Stage starts a take (26 GB
  for 14B-class performers, scaled down to 12 GB for the 5B — the playbill
  sizes each clearance from the weights on the floor),
  the booth asks ComfyUI to strike its set (`POST /free`) and then VERIFIES
  via `nvidia-smi` that the memory actually returned, refusing the cue with a
  voiced 503 if it did not. Two subtleties baked in: the `/free` flags are only
  consumed when ComfyUI's prompt worker wakes from `q.get(timeout=1000)`, so
  the guard follows them with a 1-pixel `EmptyImage → PreviewImage` "knock"
  that wakes the worker instantly; and the guard is skipped entirely when the
  requested LLM is already resident (loading it costs nothing new).
  Never weaken this back to best-effort: proceeding
  makes Ollama offload ~10 GB into system RAM on top of ComfyUI's ~21 GB
  weight cache, and that stampede OOM-killed the 31 GB WSL VM twice
  (21:00 + 21:07 on 2026-07-09), wedging the GPU bridge (`dxg` ioctl
  failures) and taking the whole distro down. Substrate half of the fix:
  `/mnt/c/Users/goost/.wslconfig` now grants `memory=44GB` + `swap=16GB`
  (effective after `wsl --shutdown`). The Promptsmith also pins
  `num_ctx: 8192` (~11.5 GB loaded instead of 14).
- **Stage UI / Face Shop UI tabs** — the full Gradio/ComfyUI houses, embedded.

**VRAM discipline** — the 5090 has 32 GB and the video models want most of it.
`qwen3:14b` loads at **14 GB** (`ollama ps` truth — the default 32k context
inflates the KV cache), so treat BOTH LLMs as non-coexistent with the diffusion
stacks: forge your prompts first, then generate. Ollama auto-unloads after
~5 min idle, but before any ComfyUI/Wan run check `ollama ps` and evict
explicitly with `ollama stop <model>`. (The Promptsmith pins `num_ctx: 8192`,
so it loads at ~11.5 GB.) This discipline is for MANUAL use of the tools —
The Prompter's Box below automates it in both directions, with a fail-closed
guard whose incident history is documented in its section.

## The Keymaster — topology-aware background keying (added with the toll arc)

`prompter-box/keymaster.py IN.mp4 OUT.webm [--crop WxH+X+Y] [--tolerance 20]
[--min-island 3000] [--crf 40] [--fps 24]` — a CLI instrument, not a booth
panel: it turns an illustrated take on a flat ground into a keyed VP9 WebM
ready for the web's `mix-blend-mode: multiply` contract.

Plain ffmpeg colorkey is purely chromatic — a tilted scroll catches the light,
lands inside the tolerance band, and gets eaten (the TC-0057 toll take lost
its wax seals to it). The Keymaster keys by topology instead:

1. Background estimated PER FRAME — median of the 10 px border ring (flat
   grounds wobble a few RGB points frame to frame).
2. Candidate pixels sit within `--tolerance` of that estimate.
3. A candidate region is keyed only if it TOUCHES the frame border (the true
   ground always does; a scroll face never does) or exceeds `--min-island`
   (an enclosed pocket of real ground, e.g. inside an arm akimbo).
4. The kept mask is feathered (1 px gaussian) and composited onto pure white.

**The one instrument excused from the stdlib rule:** it needs numpy + Pillow +
scipy, which the system python does not carry — run it with any machine's venv
python (Wan2GP, ComfyUI, and MMAudio all carry all three), e.g.
`ComfyUI/.venv/bin/python prompter-box/keymaster.py …`. It shells out to the
static ffmpeg in `~/.local/bin` for decode/encode (no torchcodec, so the
shared-libs substrate is not needed here).

## The Kiln's furniture laws (the Parlour square-back arc, 2026-08-02)

Four chair firings and two table firings for the Parlour's fixed room extended
the kiln recipe with five laws. Canonical write-up: the lab archive's
`ai-video-generation.md` §Furniture Laws; the instrument side lives in this
repo (`prompter-box/kiln.py`, `cut-stances.py`, `key-back.py`).

1. **Hunyuan cannot hold an open-air table.** A tabletop on slender legs lost
   its legs to voxelization at octree 224 AND 320 — two failures at both
   resolutions is a shape limit, not bad luck. The cure is the **hybrid law**:
   fire the PAINTING, crop it into per-face textures (top surface, edge rail,
   leg strip), and mount on procedural box geometry that can never shred —
   things that must be straight are born procedural. Chairs survive meshing
   (their backs make them chunky); tables do not. Reach for the hybrid before
   spending firings on leggy furniture meshes.
2. **The painter has a proportion CEILING — measure the painting, never trust
   the cue.** Across four cue variants the painter delivered ~40 cm backrests
   and ~7 cm cushions against explicit asks of 75 cm and 3 cm. Cue real
   anthropometrics in centimetres (it steers the right DIRECTION), then
   measure the fired painting (a brown-band row scan finds the cushion line)
   and derive the mount scale from the spec: `CHAIR_H = 0.45 / measured-seat-
   fraction` puts the seat at a true 45 cm whatever the painter did.
3. **Y-band surgery closes the last centimetres — project the painting
   FIRST.** Bake the planar UVs before remapping vertex bands: projection-
   then-surgery glues painted features to their vertices so the texture rides
   the knife. The reverse order smears the cushion pixels across the frame.
4. **Rear faces wear plain iron, and fired slabs shade like corrugation.**
   Planar projection only owns what the painting saw — split rear-facing
   triangles (face normal z < −0.15·len) onto an untextured material. Hunyuan
   sculpts painted mottling as literal surface waves that shade into arc
   bands under raking light; pull the panel region's normals to the slab
   plane, silhouette untouched.
5. **Krea RAW grounds are GRADIENTS — a flat-median keyer refuses them.**
   Ring residuals run ~80 chroma units corner-to-corner, so the old flat
   median tripped the fail-closed border check on a clean firing. The Kiln's
   `key_prop_image` now fits a quadratic background surface from the border
   ring (subject-in-ring pixels pre-trimmed so the refusal keeps firing),
   keys with tol = max(25, ring-residual p99.9 × 1.6), chroma-gates enclosed
   islands (key-green pockets between limbs always key; olive skin never
   does), and `despill_green_gate` cures spill with a laxer 3 px edge band.

**The graduated instruments** (both run with a machine venv's python, like the
Keymaster):

- `prompter-box/key-back.py SRC.jpg OUT.png` — key one still plate off its
  green gradient ground: quadratic key + strong green despill + the +6 px
  alpha-bbox crop.
- `prompter-box/cut-stances.py TAKE.mp4 OUTDIR PREFIX [N]` — the Bull's
  one-command stance cutter: stillest frame per beat window (base stance from
  the take's own EARLY frames — the seam law), quadratic key + despill per
  frame, foot-centroid registration with a zero-fill shift (never np.roll),
  union crop at +6 px so every stance shares one canvas.

## Containment — the Sentinel and the merge path (armed 2026-07-31)

`.github/workflows/sentinel.yml` runs on every push to `main` and every PR
against it. Two jobs, and neither fires the machines:

- **proscenium** — `prompter-box/front/`: `npm ci`, `npm run lint`,
  `npm run typecheck`, `npx vitest run`, `npm run check:dist`.
- **kiln-room** — `pip install numpy pillow scipy trimesh pytest`, then
  `python -m pytest prompter-box/tests/`. Fixture-driven, no GPU; pyrender is
  deliberately not installed (`turntable.py` lazy-imports it only on the real
  EGL path, which the suite never takes).

The same gates run locally with the commands in the sections above — the
pytest one wants the ComfyUI venv python. This is a PUBLIC repo, so it is
outside the Sentinel quota freeze: the runs really happen and their red is
real.

`main` is **branch-protected** — a direct push is refused with GH006. Land a
change as: fetch, branch off the `origin/main` tip, run the gates, push the
branch, `gh pr create --head <branch>`. The investor's squash-merge is the
authorization, and because a squash mints a NEW SHA, the lab's submodule
gitlink is re-pointed in the parent repo AFTER the merge (`sync(workshop): …`).
The parent's `git status` reads clean while that gitlink is stale, so the
re-point has to be deliberate.

## The stage door — the booth is a house instrument (2026-07-31)

`server.py` binds **`127.0.0.1`**, not `0.0.0.0`. The booth spawns
subprocesses and streams `footage/` — "personal media (the puppeteer's own
face among it). Never leaves the building." The old bind handed that archive
to the Windows host and to whatever the firewall's inbound posture allowed
behind it.

Browse it as **`http://localhost:7900`** from either side: WSL2's localhost
forwarding reaches the loopback bind. The VM's LAN address no longer answers,
by design. `verify-sideport.py` already bound `127.0.0.1:7901` and is
unaffected.

Two more checks stand at the door, both about the browser tab nobody opened on
purpose — the bind cannot keep those out:

- **Origin** — a request whose `Origin` is present and is not this booth's own
  (matched against the request's own `Host`, so :7901 is as much the house as
  :7900) is refused **403**. Absent `Origin` means the house itself: curl, the
  verify probes, and same-origin GETs all arrive bare.
- **Content-Type** — a POST not marked `application/json` is refused **415**.
  A POST of `text/plain` carrying JSON is a CORS *simple request*: no
  preflight, no consent, and the attacker never needs to read the reply
  because the damage is the side effect — a firing, a discard, a subprocess.
  Demanding JSON forces a preflight the booth answers with silence.

The front sends the header from `useBoothApi.ts`; any new caller must too, or
every cue 415s. `prompter-box/tests/test_server.py` holds all three behaviours
plus the traversal guards and the 409s.

## Hard-won constraints

- **Resolution discipline** — motion transfer degrades if driving video and generation
  resolution differ. That is the whole reason the crop tool (step 3) exists. Crop first,
  then feed everything at the exact same WxH.
- **pypi.nvidia.com is flaky** — CUDA wheels time out at default timeouts. Use
  `UV_HTTP_TIMEOUT=600` and sequential installs; `uv` resumes from cache.
- **No sudo** — ffmpeg/ffprobe are static builds in `~/.local/bin` (johnvansickle).
- **31 GB system RAM in WSL2** — Wan2GP is built for that ("GPU poor" profiles);
  in ComfyUI avoid loading base+distilled Klein simultaneously.
