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

## Layout

```
video-lab/
├── Wan2GP/            # deepbeepmeep/Wan2GP, .venv python 3.11, torch 2.10 cu130
├── ComfyUI/           # comfyanonymous/ComfyUI, .venv python 3.12, torch cu130
│   ├── custom_nodes/ComfyUI-GGUF/     # loads the Klein GGUF quants
│   └── models/{diffusion_models,text_encoders,vae}/
├── crop-tool/         # step 3 — exact-resolution cropper (to build)
├── start-wangp.sh     # → http://localhost:7860
└── start-comfyui.sh   # → http://localhost:8188
```

## Models

| File | Where | Source | Note |
|------|-------|--------|------|
| `flux-2-klein-9b-BF16.gguf` | `ComfyUI/models/diffusion_models/` | `unsloth/FLUX.2-klein-9B-GGUF` | ungated; full precision, ~18 GB — fits the 5090 |
| `qwen_3_8b_fp8mixed.safetensors` | `ComfyUI/models/text_encoders/` | `Comfy-Org/flux2-klein-9B` | ungated |
| `flux2-vae.safetensors` | `ComfyUI/models/vae/` | `Comfy-Org/flux2-dev` | ungated |
| `hunyuan_3d_v2.1.safetensors` | `ComfyUI/models/checkpoints/` | `Comfy-Org/hunyuan3D_2.1_repackaged` | ungated; 7.4 GB all-in-one (DiT + CLIP-vision + VAE). **The latent kiln** — image→GLB mesh via ComfyUI-native nodes (`ImageOnlyCheckpointLoader → CLIPVisionEncode → Hunyuan3Dv2Conditioning → KSampler 30 steps cfg 5 → VAEDecodeHunyuan3D → VoxelToMesh "surface net" → SaveGLB`); ~30 s per mesh on the 5090. Shape only — no texture stage in core ComfyUI; planar-project the source painting in the consumer (edge-pad the keyed texture first, seeding from interior colors so the outline ring never smears). First firing: the Menagerie's Carousel Figure (2026-07-10) |
| SCAIL-2 / OmniVoice / LTX2 | Wan2GP manages | auto-download on first use | pick in the Wan2GP UI |

**Gated upgrade path:** the official `black-forest-labs/FLUX.2-klein-9b-fp8` safetensors
are `gated: auto` on HuggingFace — log in, click agree, mint a read token, put it in
`~/.cache/huggingface/token`, then the fp8 files download fine and the GGUF node becomes
optional. Not required — BF16 GGUF is already ≥ fp8 quality.

**Character-swap extras spotted on HF (untested):** `nhathoangfoto/Flux.2-Klein-9B-SmartCharacterSwap`,
`thedeoxen/refcontrol-FLUX.2-klein-9B-reference-pose-lora`, `dx8152/Flux2-Klein-9B-Consistency`.

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

Targets: `wan` (i2v motion-first, never redescribes the start-image character),
`flux` (Klein 9B single-paragraph, positive-only), `relay` (LTX2 time-ranged
segments). All three enforce the cfg=1 lesson: distilled models ignore negative
prompts, so everything is phrased as what you WANT.

**Coding chat** — `ollama run qwen3-coder:30b-a3b-q4_K_M` for an interactive
session, or point any OpenAI-compatible client at `localhost:11434/v1`.

## The Prompter's Box — the unified console (added 2026-07-09)

`./start-prompter.sh` → **http://localhost:7900** — one booth for the whole
pipeline (stdlib Python, `prompter-box/`, no venv):

- **Forge** — the Promptsmith in a panel: idea → cue cards, each with
  copy / "Cue the stage" / "Cue the face shop" buttons.
- **The Stage** — headless Wan 2.2 i2v runs (`wgp.py --process`) using the
  bell-swing arc's Enhanced Lightning 14B recipe: pick a start image from
  `footage/`, set resolution/frames/seed, watch the log, get the video inline.
  Settings JSONs land in `jobs/prompter-*.json`, logs in `jobs/logs/`.
- **Face Shop** — headless Flux 2 Klein 9B text-to-image via the ComfyUI API
  (needs `./start-comfyui.sh` running); result renders inline in seconds.
  Every painting carries **"Send to the stage →"**: copies it into `footage/`,
  jumps to the Stage with it preselected, and snaps the resolution to the
  nearest Wan aspect — paint the character, then animate it, one click apart.
- **VRAM choreography** — cue lights show what's loaded; every generation cue
  auto-evicts loaded LLMs first; "Clear the boards" evicts by hand. Stage cues
  are refused while the full Wan2GP UI holds :7860 (one GPU, one performance).
- **The Stagehands' Guard (FAIL-CLOSED — incident 2026-07-09)** — before the
  forge loads an LLM (13 GB VRAM needed) or the Stage starts a take (26 GB),
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

## Hard-won constraints

- **Resolution discipline** — motion transfer degrades if driving video and generation
  resolution differ. That is the whole reason the crop tool (step 3) exists. Crop first,
  then feed everything at the exact same WxH.
- **pypi.nvidia.com is flaky** — CUDA wheels time out at default timeouts. Use
  `UV_HTTP_TIMEOUT=600` and sequential installs; `uv` resumes from cache.
- **No sudo** — ffmpeg/ffprobe are static builds in `~/.local/bin` (johnvansickle).
- **31 GB system RAM in WSL2** — Wan2GP is built for that ("GPU poor" profiles);
  in ComfyUI avoid loading base+distilled Klein simultaneously.
