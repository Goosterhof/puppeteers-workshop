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
| **The Prompter's Box** | `prompter-box/` (`./start-prompter.sh` → :7900) | The unified console — forge cues (voice pick from the Ollama shelf), paint in the Face Shop (headless ComfyUI, painter pick from the storeroom), animate on the Stage (headless `wgp.py --process` with a performer playbill enumerated from the weights on the floor — i2v 14B, t2v 5B, SCAIL-2 motion transfer, Krea 2 stills — each with a LoRA wardrobe off its family shelf plus steps/guidance knobs), score in the Foley Booth (headless MMAudio t2a/v2a — a Stage take is one click from its soundtrack), cast paintings into footage, all with fail-closed VRAM choreography |
| **The Promptsmith** | `prompt-forge/promptsmith.py` | Generation-prompt forge on local Ollama models — `qwen3:14b` text, `qwen3-vl:8b` with `--image` (reads the stillness inventory off the actual pixels) |
| **The Framewright** | `crop-tool/croptool.py` | Exact-resolution cropper with Wan presets — resolution discipline is the whole game in motion transfer |
| **The Keymaster** | `prompter-box/keymaster.py` | Topology-aware background keying for illustrated takes — only border-connected regions (or `--min-island` pockets) are keyed, so a scroll face can never be eaten the way plain colorkey ate the TC-0057 wax seals; outputs multiply-ready VP9 WebM. The one instrument excused from the stdlib rule (numpy + Pillow + scipy — run it with a machine venv's python; see the runbook) |
| **The Kiln Room** (bench graft pending) | `prompter-box/kiln.py` + `turntable.py` + `night_shift.py` + `stagehands.py` | The prop-firing spine (experiment log #00062): a subject phrase becomes a keyed, despilled, +6px-cropped hide and a Hunyuan3D GLB in one chain, with the Turntable's silhouette/voxel/island checks catching shredded thin structures and auto-refiring once at 224/0.4; every firing parks `pending` on the **Curing Rack** (nothing reaches `pack-queue/` without a thumb on Approve) and the **Night Shift** works a persisted call sheet overnight through the SAME `clear_the_set` guard (`stagehands.py` — the guard family extracted from server.py, one definition for every station). qwen3-vl grounds each firing and writes its Canister label. Turntable renders headless via pyrender+EGL; the shared guard rule stands unweakened. Containment: `python -m pytest prompter-box/tests/` (fixture-driven, no GPU; run with the ComfyUI venv python — see `prompter-box/requirements.txt`). Built and green in the blueprint; awaits its graft onto the bench + a live end-to-end firing before DELIVERED. |

## Conventions

- Stdlib-only Python for the instruments — no venvs of our own; the machines
  carry their own. (The Keymaster is the standing exception: its topology maths
  need numpy + Pillow + scipy, borrowed from a machine venv's python. The Kiln
  Room extends the same exception: `kiln.py`/`turntable.py` add trimesh +
  pyrender for mesh QA — declared in `prompter-box/requirements.txt`, installed
  into the ComfyUI venv, run with that venv's python.)
- Commit scope: `workshop` (see the lab's Commit Doctrine).
- Gadget containment protocols apply: the Prompter's Box carries the
  `prefers-reduced-motion` floor in its single-page CSS.
- The GPU is a one-performance stage: anything that loads a model goes through
  the Prompter's Box guard (`clear_the_set()`) or checks `nvidia-smi` first.
  Never weaken the guard to best-effort — see runbook §The Stagehands' Guard.
