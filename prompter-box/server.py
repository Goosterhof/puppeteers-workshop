#!/usr/bin/env python3
"""The Prompter's Box — the booth that feeds lines to the performers.

One console on http://localhost:7900 for the whole workshop pipeline:
forge prompts (The Promptsmith / qwen3:14b), fire them at the Face Shop
(ComfyUI Flux 2 Klein, headless) or the Stage (Wan2GP headless --process),
and watch the results — with VRAM choreography handled for you.

Stdlib only, same philosophy as the Promptsmith: no venv, no dependencies.
"""

import base64
import json
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# The crew musters in stagehands.py — the SAME fail-closed guard for every
# station (Forge, Face Shop, Stage, Foley, Kiln, Night Shift). One guard,
# many callers, zero copies to drift.
from stagehands import (  # noqa: F401  (re-exported names other rooms rely on)
    BASE, COMFY, COMFY_IN, COMFY_OUT, OLLAMA, WAN_UI_PORT,
    clear_the_set, evict_llms, gpu_vram_free_gb, gpu_vram_gb, http_json,
    loaded_llms, port_open, ram_available_gb,
)

STATIC = Path(__file__).resolve().parent / "static"
FOOTAGE = BASE / "footage"

# The stage door for stills you bring yourself (bring-your-own-sitter, 2026-08-23).
# The shelf takes the three formats every room already reads, identified by
# the bytes and never by the name the browser claimed — a .png full of HTML is
# refused at the door, not discovered by LoadImage.
STILL_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
)
STILL_CEILING_BYTES = 32 * 1024 * 1024  # a 4K PNG is ~20 MB; a 32 MB still is not a sitter


def sniff_still(data):
    """The extension the bytes earn, or None when they are not a still we shelve."""
    for magic, ext in STILL_SIGNATURES:
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def shelf_name(claimed, ext):
    """A safe, unique name on the shelf: basename only, one ASCII alphabet,
    the extension the bytes earned, and a numbered suffix when a still of
    that name already hangs there — the shelf never overwrites."""
    stem = Path(claimed.replace("\\", "/")).name
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", stem)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "still"
    candidate = f"{stem}{ext}"
    n = 2
    while (FOOTAGE / candidate).exists():
        candidate = f"{stem}-{n}{ext}"
        n += 1
    return candidate


JOBS = BASE / "jobs"
JOB_LOGS = JOBS / "logs"
WAN_DIR = BASE / "Wan2GP"
WAN_PY = WAN_DIR / ".venv" / "bin" / "python"
WAN_OUT = WAN_DIR / "outputs"
WAN_DEFAULTS = WAN_DIR / "defaults"
WAN_SETTINGS = WAN_DIR / "settings"
WAN_CKPTS = WAN_DIR / "ckpts"
WAN_LORAS = WAN_DIR / "loras"
COMFY_PAINTERS = BASE / "ComfyUI" / "models" / "diffusion_models"
MM_DIR = BASE / "MMAudio"
MM_PY = MM_DIR / ".venv" / "bin" / "python"
MM_OUT = MM_DIR / "output" / "prompter"
FF_SHARED = BASE / "ffmpeg-shared" / "lib"  # torchcodec's substrate — see the runbook

PORT = 7900
HOUSE_HOST = "127.0.0.1"  # the booth is a house instrument, not a broadcast

# The stage door. Two checks, both about the browser tab nobody opened on
# purpose. The bind above already keeps the LAN out; these keep the OTHER
# TABS out, which the bind cannot:
#   * Origin is browser-set and unforgeable by page script. It is absent on
#     same-origin GETs and on every non-browser caller (curl, the side-port
#     verify probes), so an absent Origin is the house itself. A PRESENT
#     Origin that is not this booth's own is another site knocking.
#   * Content-Type decides whether a cross-site POST needs the browser's
#     permission first. A POST of text/plain carrying JSON is a CORS *simple
#     request* — no preflight, no consent — and the attacker never needs to
#     read the reply, because the damage IS the side effect: a firing, a
#     discard, a subprocess. Demanding application/json forces a preflight
#     the booth answers with silence.
CUE_SHEET_TYPE = "application/json"

sys.path.insert(0, str(BASE / "prompt-forge"))
from promptsmith import DEFAULT_MODEL, FORGE_PROFILES, VISION_MODEL, forge  # noqa: E402

import kiln  # noqa: E402  — the firing chain + the Curing Rack's tray
import night_shift  # noqa: E402  — the overnight call sheet (blueprint file: night_shift.py)
import pins  # noqa: E402  — the Pinboard: named recipes promoted from proven takes (#08)
from turntable import turntable_qa  # noqa: E402  — one instrument, two consumers

# The house lead — the arc-proven Wan 2.2 i2v Enhanced Lightning recipe
# (jobs/crier-bell-14b.json). Other performers join the playbill dynamically:
# any Wan2GP model type whose weights are actually on the floor (see
# stage_playbill) becomes selectable, with its recipe layered from the
# model's defaults JSON plus the bench's own saved UI settings.
DEFAULT_PERFORMER = "i2v_2_2_Enhanced_Lightning_v2"

# What each performer expects at the stage door. Kinds:
#   i2v  — video from a start image (lead required)
#   t2v  — video from text (lead optional)
#   swap — motion transfer (lead = the character, plus a driving video)
#   t2i  — a still image (no lead, no frames)
PERFORMER_NOTES = {
    "i2v_2_2_Enhanced_Lightning_v2":
        "The identity-holding recipe from the bell-swing arc. Once motion reads, "
        "iterate by seed, not prompt. A 41-frame take denoises in ~1 min.",
    "ti2v_2_2":
        "The 5B — a lighter performer that works from text alone; hand it a lead "
        "and it starts from the image instead. 50 undistilled steps: slower per "
        "frame than the Lightning 14B, but it fits the GPU with room to spare.",
    "scail2_14B":
        "Motion transfer — the lead is the CHARACTER, the driving video is the "
        "CHOREOGRAPHY. It re-performs the driving video's motion with your "
        "character. 40 steps; budget several minutes per take.",
    "krea2_raw":
        "An image performer on the Stage's boards — Krea 2 RAW paints one still "
        "per cue (52 CFG-guided steps). No frames, no lead; resolution and seed "
        "are the whole conversation.",
}


def performer_kind(model_type, arch):
    a = (arch or model_type or "").lower()
    if a.startswith(("krea2", "flux", "qwen_image", "z_image", "ideogram", "hidream")):
        return "t2i"
    if "scail" in a or a in ("animate", "steadydancer", "wanmove"):
        return "swap"
    if a == "ti2v_2_2" or a.startswith("t2v"):
        return "t2v"
    return "i2v"


def lora_shelf(model_type, arch):
    """Which LoRA drawer this performer dresses from.

    Mirrors the family handlers' get_lora_dir branching (wan_handler.py:143,
    krea2_handler.py) without importing them — the handlers drag in torch.
    """
    a = (arch or model_type or "").lower()
    for family in ("krea2", "flux", "qwen", "ltxv", "hunyuan"):
        if a.startswith(family):
            return WAN_LORAS / family
    if a in ("ti2v_2_2", "lucy_edit", "kiwi_edit"):
        return WAN_LORAS / "wan_5B"
    if "1.3b" in a:
        return WAN_LORAS / "wan_1.3B"
    # i2v-class EXCEPT the 2.2 family dresses from wan_i2v; the 2.2 models
    # (i2v_2_2 and kin) share the base wan drawer with t2v.
    if ("scail" in a or a in ("i2v", "fun_inp", "flf2v_720p", "fantasy",
                              "multitalk", "infinitetalk", "animate")):
        return WAN_LORAS / "wan_i2v"
    return WAN_LORAS / "wan"


def shelf_loras(shelf):
    try:
        return sorted(p.name for p in shelf.iterdir() if p.suffix.lower() == ".safetensors")
    except OSError:
        return []


def stage_playbill():
    """Every Wan2GP model type whose weights are actually on the floor.

    A defaults JSON earns its playbill seat only when at least one file from
    URLs (and URLs2, when the model swaps weights mid-run) is present in
    ckpts/ — and, when the model rides on a named LoRA set (SVI 2 Pro), the
    LoRA is present too. Anything else would be a lie that ends in a
    multi-GB surprise download mid-cue.
    """
    try:
        installed = {p.name: p.stat().st_size for p in WAN_CKPTS.iterdir() if p.is_file()}
    except OSError:
        return []
    def present(urls):
        if not isinstance(urls, list):
            return []
        names = [u.rsplit("/", 1)[-1] for u in urls if isinstance(u, str) and u.startswith("http")]
        return [n for n in names if n in installed]
    playbill = []
    for f in sorted(WAN_DEFAULTS.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        m = d.get("model") or {}
        w1, w2 = present(m.get("URLs")), present(m.get("URLs2"))
        if not w1 or (isinstance(m.get("URLs2"), list) and m["URLs2"] and not w2):
            continue
        if (lora_ref := m.get("loras")) and isinstance(lora_ref, str):
            if not list(WAN_LORAS.glob(f"**/*{lora_ref}*")):
                continue  # the finetune's LoRA never made it to the floor
        # Recipe layering: model defaults, then the bench's own saved UI
        # settings for this type — the numbers a human actually dialed in.
        recipe = {k: v for k, v in d.items() if k not in ("model", "prompt")}
        saved = WAN_SETTINGS / f"{f.stem}_settings.json"
        if saved.exists():
            try:
                s = json.loads(saved.read_text())
                s.pop("prompt", None)
                s.pop("settings_version", None)
                recipe.update(s)
            except (OSError, json.JSONDecodeError):
                pass
        largest_gb = max(installed[n] for n in w1 + w2) / 1e9
        kind = performer_kind(f.stem, m.get("architecture"))
        shelf = lora_shelf(f.stem, m.get("architecture"))
        playbill.append({
            "type": f.stem,
            "name": m.get("name") or f.stem,
            "kind": kind,
            # 14B-class weights earned the proven 26 GB clearance; smaller
            # performers scale down so the guard never over-refuses.
            "vram_gb": 26 if largest_gb >= 10 else 18 if largest_gb >= 6 else 12,
            "resolution": recipe.get("resolution") or ("1024x1024" if kind == "t2i" else "704x1280"),
            "video_length": recipe.get("video_length", 41),
            "steps": recipe.get("num_inference_steps", 30),
            "guidance": recipe.get("guidance_scale", 5),
            "loras": shelf_loras(shelf),
            "lora_shelf": shelf.name,
            "note": PERFORMER_NOTES.get(f.stem, ""),
            "recipe": recipe,
        })
    return playbill

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
VIDEO_EXTS = (".mp4", ".webm", ".mkv")
FFPROBE = shutil.which("ffprobe") or str(Path.home() / ".local" / "bin" / "ffprobe")

stage_lock = threading.Lock()
stage_job = {"state": "idle"}  # idle | running | done | failed

foley_lock = threading.Lock()
foley_job = {"state": "idle"}  # idle | running | done | failed

kiln_lock = threading.Lock()
kiln_job = {"state": "idle"}   # idle | running | done | failed
shift_log = {"name": None}     # the Night Shift's current log reel


def stations_clear():
    """The Night Shift's door check — the floor must be free before a row
    lights. This is the SAME containment every station lives under: no
    Stage or Foley take mid-performance, no Kiln-tab firing, no full UI
    holding the GPU. VRAM residency itself is struck by clear_the_set at
    every swap boundary inside the firing chain."""
    return (stage_job.get("state") != "running"
            and foley_job.get("state") != "running"
            and kiln_job.get("state") != "running"
            and not port_open(WAN_UI_PORT))


def kiln_log_writer(log_path):
    def say(msg):
        with open(log_path, "a") as fh:
            fh.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    return say


def run_kiln_job(work, log_path):
    """Background body for a Kiln firing or a Rack refire — mirrors
    run_stage_job's shape: state dict, log reel, voiced failure."""
    global kiln_job
    say = kiln_log_writer(log_path)
    try:
        result = work(say)
        kiln_job.update({"state": "done", **result,
                         "finished": datetime.now().isoformat(timespec="seconds")})
    except (kiln.KilnColdError, kiln.KilnRefusal, kiln.RackRefusal) as e:
        say(str(e))
        kiln_job.update({"state": "failed", "error": str(e),
                         "finished": datetime.now().isoformat(timespec="seconds")})
    except Exception as e:  # a firing must never die silently overnight
        say(f"the kiln cracked unexpectedly: {e!r}")
        kiln_job.update({"state": "failed",
                         "error": f"The kiln cracked unexpectedly — {e}. The log reel has the shard.",
                         "finished": datetime.now().isoformat(timespec="seconds")})


def night_shift_take(row, _take_index, subject, seed):
    """One Night Shift take = the full Kiln chain + the Turntable's appraisal,
    exactly as a manual firing — the Rack cannot tell them apart."""
    say = kiln_log_writer(JOB_LOGS / shift_log["name"]) if shift_log["name"] else (lambda _m: None)
    result = kiln.kiln_fire(
        subject,
        octree=int(row.get("octree", 128)),
        threshold=float(row.get("threshold", 0.5)),
        two_sided=bool(row.get("two_sided", False)),
        seed=seed,
        clear_set=clear_the_set,
        log=say,
    )
    kiln.appraise_candidate(result.id, clear_set=clear_the_set)
    return result


def start_night_shift():
    """Put the shift on the floor with the booth's own wiring."""
    JOB_LOGS.mkdir(parents=True, exist_ok=True)
    shift_log["name"] = f"night-shift-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    say = kiln_log_writer(JOB_LOGS / shift_log["name"])
    return night_shift.start_shift(night_shift_take, stations_clear, log=say)


DEFAULT_PAINTER = "flux-2-klein-9b-BF16.gguf"


def face_painters():
    """Diffusion models hanging in the Face Shop's storeroom."""
    try:
        return sorted(p.name for p in COMFY_PAINTERS.iterdir()
                      if p.suffix.lower() in (".gguf", ".safetensors"))
    except OSError:
        return []


def klein_graph(prompt, width, height, seed, steps, prefix="PrompterBox", painter=DEFAULT_PAINTER):
    # GGUF painters load through the GGUF door, safetensors through the
    # standard one. The qwen3 text encoder and flux2 VAE are bolted to the
    # easel — only Flux 2 family painters will pair with them.
    loader = (
        {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": painter}}
        if painter.lower().endswith(".gguf")
        else {"class_type": "UNETLoader", "inputs": {"unet_name": painter, "weight_dtype": "default"}}
    )
    return {
        "1": loader,
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "cfg": 1.0}},
        "7": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "8": {"class_type": "Flux2Scheduler", "inputs": {"steps": steps, "width": width, "height": height}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "10": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["9", 0], "guider": ["6", 0], "sampler": ["7", 0], "sigmas": ["8", 0], "latent_image": ["10", 0]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": prefix}},
    }


def klein_edit_graph(prompt, seed, steps, prefix, painter, source_name):
    """Image editing — the arc-proven ReferenceLatent recipe (the same graph
    that repainted the night crier, recovered from the archive's own PNG
    labels). The source is scaled to ~1 MP and the output follows its
    dimensions; the cue describes the change, not the whole picture."""
    loader = (
        {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": painter}}
        if painter.lower().endswith(".gguf")
        else {"class_type": "UNETLoader", "inputs": {"unet_name": painter, "weight_dtype": "default"}}
    )
    return {
        "load": {"class_type": "LoadImage", "inputs": {"image": source_name}},
        "scale": {"class_type": "ImageScaleToTotalPixels",
                  "inputs": {"image": ["load", 0], "upscale_method": "nearest-exact",
                             "megapixels": 1.0, "resolution_steps": 1}},
        "size": {"class_type": "GetImageSize", "inputs": {"image": ["scale", 0]}},
        "unet": loader,
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors", "type": "flux2"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["clip", 0]}},
        "neg0": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["pos", 0]}},
        "venc": {"class_type": "VAEEncode", "inputs": {"pixels": ["scale", 0], "vae": ["vae", 0]}},
        "refpos": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["pos", 0], "latent": ["venc", 0]}},
        "refneg": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["neg0", 0], "latent": ["venc", 0]}},
        "guider": {"class_type": "CFGGuider",
                   "inputs": {"model": ["unet", 0], "positive": ["refpos", 0], "negative": ["refneg", 0], "cfg": 1.0}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "sched": {"class_type": "Flux2Scheduler",
                  "inputs": {"steps": steps, "width": ["size", 0], "height": ["size", 1]}},
        "latent": {"class_type": "EmptyFlux2LatentImage",
                   "inputs": {"width": ["size", 0], "height": ["size", 1], "batch_size": 1}},
        "samp": {"class_type": "SamplerCustomAdvanced",
                 "inputs": {"noise": ["noise", 0], "guider": ["guider", 0], "sampler": ["sampler", 0],
                            "sigmas": ["sched", 0], "latent_image": ["latent", 0]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["samp", 0], "vae": ["vae", 0]}},
        "save": {"class_type": "SaveImage", "inputs": {"images": ["dec", 0], "filename_prefix": prefix}},
    }


def run_stage_job(settings_path, log_path):
    global stage_job
    before = {p.name for p in WAN_OUT.glob("*")} if WAN_OUT.exists() else set()
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(
            [str(WAN_PY), "wgp.py", "--process", str(settings_path), "--output-dir", str(WAN_OUT)],
            cwd=WAN_DIR, stdout=log, stderr=subprocess.STDOUT,
        )
        stage_job.update({"pid": proc.pid})
        code = proc.wait()
    new = sorted({p.name for p in WAN_OUT.glob("*")} - before) if WAN_OUT.exists() else []
    # Video performers land reels; image performers (Krea 2) land stills.
    media = [n for n in new
             if n.lower().endswith((".mp4", ".webm", ".mkv", ".png", ".jpg", ".jpeg", ".webp"))]
    stage_job.update(
        {
            "state": "done" if code == 0 and media else "failed",
            "exit_code": code,
            "outputs": media or new,
            "finished": datetime.now().isoformat(timespec="seconds"),
        }
    )


def run_foley_job(cmd, log_path, out_dir):
    global foley_job
    # torchcodec dlopens the FFmpeg SHARED libs — the booth injects the substrate
    # so the Foley Booth works from any shell (the static binaries carry no .so).
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = ":".join(filter(None, [str(FF_SHARED), env.get("LD_LIBRARY_PATH")]))
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(cmd, cwd=MM_DIR, stdout=log, stderr=subprocess.STDOUT, env=env)
        foley_job.update({"pid": proc.pid})
        code = proc.wait()
    new_files = sorted(
        p.name for p in out_dir.glob("*") if p.suffix.lower() in (".flac", ".mp4")
    ) if out_dir.exists() else []
    foley_job.update(
        {
            "state": "done" if code == 0 and new_files else "failed",
            "exit_code": code,
            "outputs": [f"{out_dir.name}/{n}" for n in new_files],
            "finished": datetime.now().isoformat(timespec="seconds"),
        }
    )


_label_cache = {}  # str(path) -> (mtime, meta)


def canister_meta(path, mtime, meta_fn):
    key = str(path)
    hit = _label_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        meta = meta_fn(path)
    except Exception:
        meta = {}  # an unreadable label never blocks the shelf
    _label_cache[key] = (mtime, meta)
    return meta


def ffprobe_format(path):
    out = subprocess.run(
        [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, timeout=15,
    )
    return json.loads(out.stdout or "{}").get("format", {})


def stage_label(path):
    """Wan2GP writes its entire settings dict into the mp4 comment tag."""
    meta = {}
    fmt = ffprobe_format(path)
    if (d := fmt.get("duration")):
        meta["duration_s"] = round(float(d), 1)
    try:
        cfg = json.loads(fmt.get("tags", {}).get("comment", ""))
    except (json.JSONDecodeError, TypeError):
        cfg = {}
    for src, dst in (("prompt", "prompt"), ("seed", "seed"),
                     ("num_inference_steps", "steps"), ("guidance_scale", "guidance"),
                     ("resolution", "resolution"), ("video_length", "frames"),
                     ("model_type", "model"), ("model_filename", "model"),
                     ("activated_loras", "loras")):
        if dst not in meta and cfg.get(src) not in (None, "", []):
            meta[dst] = cfg[src]
    if isinstance(meta.get("loras"), list):
        meta["loras"] = [Path(str(l)).stem for l in meta["loras"]]
    if isinstance(meta.get("model"), str):
        meta["model"] = Path(meta["model"]).stem
    return meta


def png_text_chunks(path, cap=1 << 20):
    data = path.read_bytes()
    pos, out = 8, {}
    while pos < min(len(data), cap) - 8:
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        if typ in (b"tEXt", b"iTXt"):
            key, _, val = data[pos + 8:pos + 8 + ln].partition(b"\x00")
            out[key.decode(errors="replace")] = val.lstrip(b"\x00").decode(errors="replace")
        if typ == b"IDAT":
            break
        pos += 12 + ln
    return out


def painting_label(path):
    """ComfyUI embeds the API graph in the PNG 'prompt' text chunk —
    booth cues and full-UI paintings alike. Walk it defensively."""
    meta = {}
    if path.suffix.lower() != ".png":
        return meta
    graph = json.loads(png_text_chunks(path).get("prompt", "{}"))
    dims = {}
    for node in graph.values():
        ct, inputs = node.get("class_type", ""), node.get("inputs", {})
        if ct == "CLIPTextEncode" and isinstance(inputs.get("text"), str) and "prompt" not in meta:
            meta["prompt"] = inputs["text"]
        for k in ("unet_name", "ckpt_name"):
            if isinstance(inputs.get(k), str) and "model" not in meta:
                meta["model"] = Path(inputs[k]).stem
        for k in ("noise_seed", "seed"):
            if isinstance(inputs.get(k), int) and "seed" not in meta:
                meta["seed"] = inputs[k]
        if isinstance(inputs.get("steps"), int) and "steps" not in meta:
            meta["steps"] = inputs["steps"]
        if isinstance(inputs.get("width"), int) and isinstance(inputs.get("height"), int):
            dims = {"resolution": f"{inputs['width']}x{inputs['height']}"}
    return meta | dims


def foley_label(path):
    """MMAudio names files by prompt slug inside a per-cue stamp dir."""
    meta = {"prompt": path.stem.replace("_", " ").strip()}
    if (d := ffprobe_format(path).get("duration")):
        meta["duration_s"] = round(float(d), 1)
    return meta


def tail_lines(path, n=25):
    try:
        raw = Path(path).read_bytes()[-16384:].decode(errors="replace")
        lines = [l.rstrip() for l in raw.replace("\r", "\n").splitlines() if l.strip()]
        return lines[-n:]
    except OSError:
        return []


class BoothWindow(BaseHTTPRequestHandler):
    """The service hatch — every request to the booth passes through here."""

    def log_message(self, *args):
        pass

    # -- plumbing ------------------------------------------------------
    def reply(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def fail(self, message, status=400):
        self.reply({"error": message}, status)

    def body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    # -- the stage door -------------------------------------------------
    def foreign_knock(self):
        """The Origin the caller knocked from, or None when it is the house.

        Matched against this request's own Host rather than a hardcoded
        :7900 — the side-port verify booth lives on :7901 and is every bit
        as much the house as the investor's console is.
        """
        origin = (self.headers.get("Origin") or "").strip().lower()
        if not origin:
            return None  # no browser, or a same-origin GET — the house itself
        host = (self.headers.get("Host") or "").strip().lower()
        if host and origin in (f"http://{host}", f"https://{host}"):
            return None
        return origin

    def door_refusal(self, posting):
        """One voiced refusal for every way a caller fails the stage door."""
        if (knock := self.foreign_knock()):
            return (f"That cue was shouted in from {knock} — the booth only takes lines "
                    "from its own console. Open the Prompter's Box on this port and cue "
                    "from there.", 403)
        if not posting:
            return None
        marked = (self.headers.get("Content-Type") or "").partition(";")[0].strip().lower()
        if marked != CUE_SHEET_TYPE:
            return (f"The booth takes cue sheets marked {CUE_SHEET_TYPE} — this one arrived "
                    f"{f'marked {marked}' if marked else 'unmarked'}. Send the cue with a JSON "
                    "content type and the window opens.", 415)
        return None

    def send_file(self, root, rel):
        target = (root / rel).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            return self.fail("That reel is not in the archive.", 404)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with open(target, "rb") as fh:
            shutil.copyfileobj(fh, self.wfile)

    # -- routes --------------------------------------------------------
    def do_GET(self):
        if (refusal := self.door_refusal(posting=False)):
            return self.fail(*refusal)
        path, _, query = self.path.partition("?")
        path = urllib.parse.unquote(path)
        if path in ("/", "/index.html"):
            return self.send_file(STATIC, "index.html")
        if path.startswith("/static/"):
            # the Potter's Wheel and its vendored three.js live here
            return self.send_file(STATIC, path[len("/static/"):])
        if path.startswith("/footage/"):
            return self.send_file(FOOTAGE, path[len("/footage/"):])
        if path.startswith("/face-output/"):
            return self.send_file(COMFY_OUT, path[len("/face-output/"):])
        if path.startswith("/stage-output/"):
            return self.send_file(WAN_OUT, path[len("/stage-output/"):])
        if path.startswith("/foley-output/"):
            return self.send_file(MM_OUT, path[len("/foley-output/"):])
        if path.startswith("/kiln-output/"):
            return self.send_file(kiln.KILN_OUT, path[len("/kiln-output/"):])
        if path.startswith("/pack-queue/"):
            return self.send_file(kiln.PACK_QUEUE, path[len("/pack-queue/"):])
        if path == "/api/shelf/list":
            return self.api_shelf_list()
        if path == "/api/status":
            return self.api_status()
        if path == "/api/kiln/job":
            return self.api_kiln_job()
        if path == "/api/rack/list":
            return self.api_rack_list()
        if path == "/api/queue/list":
            return self.api_queue_list()
        if path == "/api/archive":
            return self.api_archive()
        if path == "/api/pins":
            return self.reply({"pins": pins.load_pins()})
        if path == "/api/footage":
            return self.api_footage()
        if path == "/api/stage/job":
            return self.api_stage_job()
        if path == "/api/stage/models":
            return self.api_stage_models()
        if path == "/api/face/models":
            return self.api_face_models()
        if path == "/api/forge/models":
            return self.api_forge_models()
        if path == "/api/foley/job":
            return self.api_foley_job()
        if path == "/api/foley/sources":
            return self.api_foley_sources()
        if path.startswith("/api/face/result/"):
            return self.api_face_result(path.rsplit("/", 1)[-1])
        self.fail("The booth has no such window.", 404)

    def do_POST(self):
        if (refusal := self.door_refusal(posting=True)):
            return self.fail(*refusal)
        try:
            payload = self.body_json()
        except json.JSONDecodeError:
            return self.fail("The cue sheet is not valid JSON.")
        route = {
            "/api/forge": self.api_forge,
            "/api/evict": self.api_evict,
            "/api/face/generate": self.api_face_generate,
            "/api/stage/generate": self.api_stage_generate,
            "/api/stage/cast": self.api_stage_cast,
            "/api/footage/upload": self.api_footage_upload,
            "/api/take/discard": self.api_take_discard,
            "/api/foley/generate": self.api_foley_generate,
            "/api/kiln/generate": self.api_kiln_generate,
            "/api/rack/approve": self.api_rack_approve,
            "/api/rack/refire": self.api_rack_refire,
            "/api/rack/discard": self.api_rack_discard,
            "/api/turntable/run": self.api_turntable_run,
            "/api/queue/add": self.api_queue_add,
            "/api/queue/remove": self.api_queue_remove,
            "/api/queue/reorder": self.api_queue_reorder,
            "/api/queue/start": self.api_queue_start,
            "/api/queue/stop": self.api_queue_stop,
            "/api/pins/pin": self.api_pins_pin,
            "/api/pins/unpin": self.api_pins_unpin,
        }.get(self.path)
        if not route:
            return self.fail("The booth has no such window.", 404)
        route(payload)

    # -- api -----------------------------------------------------------
    def api_status(self):
        llms = loaded_llms()
        comfy = None
        try:
            stats = http_json(f"{COMFY}/system_stats", timeout=2)
            dev = stats["devices"][0]
            comfy = {"up": True, "vram_free_gb": round(dev["vram_free"] / 1e9, 1),
                     "vram_total_gb": round(dev["vram_total"] / 1e9, 1)}
            # Chaos #00085 detonation 1: without the /queue probe the Face
            # Shop plate could never go LIVE — a running paint (booth-cued
            # or full-UI) showed "warm". A failed probe reads not-painting,
            # never a fake performance.
            try:
                comfy["painting"] = bool(http_json(f"{COMFY}/queue", timeout=2).get("queue_running"))
            except (OSError, LookupError, AttributeError):
                comfy["painting"] = False
        except (OSError, LookupError):
            comfy = {"up": False}
        # Chaos #00085 detonation 2: the dimmer's fallback — driver truth via
        # nvidia-smi, so the meter never reads "no meter" while the GPU is
        # alive just because ComfyUI is dark.
        gpu = None
        if (vram := gpu_vram_gb()) is not None:
            gpu = {"vram_free_gb": round(vram[0], 1), "vram_total_gb": round(vram[1], 1)}
        self.reply({
            "forge": {"up": llms is not None,
                      "loaded": [{"model": m["model"], "size_gb": round(m.get("size", 0) / 1e9, 1)}
                                 for m in llms or []]},
            "face_shop": comfy,
            "gpu": gpu,
            "stage_ui": {"up": port_open(WAN_UI_PORT)},
            "stage_job": {k: v for k, v in stage_job.items() if k != "pid"},
            "foley": {"installed": MM_PY.exists(),
                      "job_state": foley_job.get("state", "idle")},
            "kiln": {"job_state": kiln_job.get("state", "idle"),
                     "act": kiln_job.get("act"),
                     "subject": kiln_job.get("subject")},
            "night_shift": night_shift.shift_status(),
        })

    def api_archive(self):
        """The canisters — every previous take still hanging in the output rooms.

        The booth itself is stateless between page loads; this window reads
        history straight from the filesystem, newest first, and reads each
        canister's label: Wan2GP embeds its full settings in the mp4 comment
        tag (metadata_type "metadata"), ComfyUI embeds the graph in PNG text
        chunks. Probed once per file, cached by mtime.
        """
        def rack(root, exts, meta_fn, recurse=False, limit=150):
            if not root.exists():
                return []
            items = []
            for p in (root.glob("**/*") if recurse else root.iterdir()):
                if p.is_file() and p.suffix.lower() in exts:
                    st = p.stat()
                    kind = ("image" if p.suffix.lower() in IMAGE_EXTS
                            else "audio" if p.suffix.lower() == ".flac" else "video")
                    items.append({"name": str(p.relative_to(root)),
                                  "mtime": int(st.st_mtime), "size": st.st_size,
                                  "kind": kind,
                                  "meta": canister_meta(p, st.st_mtime, meta_fn)})
            items.sort(key=lambda x: -x["mtime"])
            return items[:limit]
        self.reply({
            "stage": rack(WAN_OUT, VIDEO_EXTS + IMAGE_EXTS, stage_label),
            "face": rack(COMFY_OUT, IMAGE_EXTS, painting_label),
            "foley": rack(MM_OUT, (".flac", ".mp4"), foley_label, recurse=True),
        })

    def api_footage(self):
        images = sorted(p.name for p in FOOTAGE.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
        self.reply({"images": images})

    def api_footage_upload(self, p):
        """Bring your own still — shelve an image from the browser into footage/.

        The front reads the file and hands it in as base64 inside the JSON cue
        sheet, so the upload walks through the SAME stage door as every other
        cue (Origin + application/json): no multipart parser, no second door
        to guard. Once shelved the still is a sitter for the Face Shop, a lead
        for the Forge, and a start image for the Stage — one shelf, three rooms.
        """
        raw = (p.get("data") or "")
        if isinstance(raw, str) and raw.startswith("data:"):
            raw = raw.partition(",")[2]  # a data: URL — strip the header the browser adds
        try:
            data = base64.b64decode(raw or "", validate=True)
        except (ValueError, TypeError):
            return self.fail("The still arrived garbled — the booth could not read it as base64. "
                             "Try the file again.")
        if not data:
            return self.fail("Nothing arrived — the upload carried no image. Pick a still and try again.")
        if len(data) > STILL_CEILING_BYTES:
            return self.fail(f"That still weighs {len(data) / 1e6:.0f} MB — the shelf takes up to "
                             f"{STILL_CEILING_BYTES // (1024 * 1024)} MB. Export it smaller and bring it back.", 413)
        ext = sniff_still(data)
        if not ext:
            return self.fail("The shelf takes stills only — PNG, JPEG, or WebP. That file opened as "
                             "something else; export it as one of the three and bring it back.", 415)
        name = shelf_name(str(p.get("name") or "still"), ext)
        FOOTAGE.mkdir(parents=True, exist_ok=True)
        # Land it whole or not at all: a browser that drops mid-upload must never
        # leave a torn still that LoadImage trips over later.
        staging = FOOTAGE / f".{name}.part"
        staging.write_bytes(data)
        os.replace(staging, FOOTAGE / name)
        self.reply({"shelved": name, "bytes": len(data)})

    def api_forge(self, p):
        target = p.get("target")
        if target not in FORGE_PROFILES:
            return self.fail(f"The Promptsmith forges no '{target}' — targets: {sorted(FORGE_PROFILES)}.")
        idea = (p.get("idea") or "").strip()
        if not idea:
            return self.fail("The forge needs raw material — give it an idea.")
        ram = ram_available_gb()
        if ram is not None and ram < 6:
            return self.fail(
                f"The booth is low on air — only {ram:.1f} GB of system RAM available. "
                "Loading the Promptsmith now risks bringing the whole house down. "
                "Close something heavy, then strike again.", 503)
        image_b64 = None
        if (image := (p.get("image") or "").strip()):
            lead = (FOOTAGE / image).resolve()
            if not lead.is_relative_to(FOOTAGE.resolve()) or not lead.is_file():
                return self.fail(f"'{image}' is not in the footage archive.", 404)
            import base64
            image_b64 = base64.b64encode(lead.read_bytes()).decode()
        model = p.get("model") or (VISION_MODEL if image_b64 else DEFAULT_MODEL)
        loaded = {m["model"] for m in loaded_llms() or []}
        if model not in loaded:
            if loaded:
                evict_llms()  # a different LLM holds the GPU — its seat is needed
            # The vision model is a featherweight (~8 GB); the text model needs 13.
            need = 8 if image_b64 else 13
            ok, free = clear_the_set(min_vram_gb=need)
            if not ok:
                return self.fail(
                    f"The stagehands could not clear the GPU for the Promptsmith — {free:.1f} GB "
                    f"free, {need} needed. The Face Shop is refusing to strike its set; give it a "
                    "moment and strike again, or restart ComfyUI if it will not let go.", 503)
        try:
            text = forge(target, idea, int(p.get("variants", 3)), model,
                         bool(p.get("think", True)), image_b64)
        except urllib.error.URLError:
            return self.fail("The forge is cold — Ollama is not answering on :11434. "
                             "Light it with `ollama serve`, then strike again.", 502)
        self.reply({"variants": split_variants(text), "raw": text, "model": model})

    def api_evict(self, _p):
        self.reply({"evicted": evict_llms()})

    def api_forge_models(self):
        """Every voice on the Ollama shelf, so the forge is not stuck with two."""
        try:
            tags = http_json(f"{OLLAMA}/api/tags", timeout=3).get("models", [])
        except OSError:
            return self.reply({"models": [], "default_text": DEFAULT_MODEL,
                               "default_vision": VISION_MODEL})
        self.reply({
            "models": sorted(m["name"] for m in tags),
            "default_text": DEFAULT_MODEL,
            "default_vision": VISION_MODEL,
        })

    def api_face_models(self):
        painters = face_painters()
        self.reply({
            "painters": painters,
            "default": DEFAULT_PAINTER if DEFAULT_PAINTER in painters
                       else (painters[0] if painters else None),
        })

    def api_face_generate(self, p):
        prompt = (p.get("prompt") or "").strip()
        if not prompt:
            return self.fail("The Face Shop paints nothing from an empty cue.")
        painter = (p.get("model") or DEFAULT_PAINTER).strip()
        if painter not in face_painters():
            return self.fail(f"No painter named '{painter}' hangs in the storeroom — "
                             "check /api/face/models for the roster.", 404)
        source = None
        if (sitter := (p.get("source") or "").strip()):
            source = (FOOTAGE / sitter).resolve()
            if not source.is_relative_to(FOOTAGE.resolve()) or not source.is_file():
                return self.fail(f"'{sitter}' is not in the footage archive.", 404)
        if stage_job.get("state") == "running":
            return self.fail("The Stage is mid-performance — the GPU cannot serve two masters. "
                             "Wait for the take to finish.", 409)
        evicted = evict_llms()
        # Unique prefix per cue: an exact repeat (same prompt+seed) would otherwise
        # be fully served from ComfyUI's cache — SaveImage skipped, no file, and the
        # take looks failed. A fresh prefix forces SaveImage to run (instant, cached
        # tensor) so every cue lands an image.
        stamp = datetime.now().strftime("%H%M%S")
        seed = int(p.get("seed", int(time.time()) % 2**31))
        steps = int(p.get("steps", 4))
        if source:
            # LoadImage reads from ComfyUI's input room — hand the sitter in.
            sitter_name = f"prompter-src-{stamp}{source.suffix.lower()}"
            COMFY_IN.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, COMFY_IN / sitter_name)
            graph = klein_edit_graph(prompt, seed, steps,
                                     prefix=f"PrompterBox-{stamp}", painter=painter,
                                     source_name=sitter_name)
        else:
            graph = klein_graph(prompt, int(p.get("width", 768)), int(p.get("height", 1024)),
                                seed, steps, prefix=f"PrompterBox-{stamp}", painter=painter)
        try:
            res = http_json(f"{COMFY}/prompt", {"prompt": graph}, timeout=15)
        except OSError:
            return self.fail("The Face Shop is dark — ComfyUI is not answering on :8188. "
                             "Raise it with ./start-comfyui.sh.", 502)
        self.reply({"prompt_id": res["prompt_id"], "evicted": evicted})

    def api_face_result(self, prompt_id):
        try:
            hist = http_json(f"{COMFY}/history/{urllib.parse.quote(prompt_id)}", timeout=5)
        except OSError:
            return self.fail("The Face Shop is dark — ComfyUI is not answering on :8188.", 502)
        if prompt_id not in hist:
            return self.reply({"state": "painting"})
        entry = hist[prompt_id]
        if entry["status"].get("status_str") == "error":
            return self.reply({"state": "failed", "detail": entry["status"].get("messages", [])})
        images = [img["filename"] for node in entry.get("outputs", {}).values()
                  for img in node.get("images", [])]
        self.reply({"state": "done", "images": images})

    def api_stage_models(self):
        bill = stage_playbill()
        self.reply({
            "models": [{k: v for k, v in m.items() if k != "recipe"} for m in bill],
            "default": DEFAULT_PERFORMER if any(m["type"] == DEFAULT_PERFORMER for m in bill)
                       else (bill[0]["type"] if bill else None),
        })

    def resolve_reel(self, ref):
        """'footage:name' or 'stage:name' → a verified path, or None."""
        source, _, name = (ref or "").partition(":")
        root = WAN_OUT if source == "stage" else FOOTAGE
        target = (root / name).resolve() if name else None
        if target and target.is_relative_to(root.resolve()) and target.is_file():
            return target
        return None

    def api_stage_generate(self, p):
        global stage_job
        prompt = (p.get("prompt") or "").strip()
        if not prompt:
            return self.fail("The Stage needs a cue (prompt).")
        model_type = (p.get("model_type") or DEFAULT_PERFORMER).strip()
        performer = next((m for m in stage_playbill() if m["type"] == model_type), None)
        if not performer:
            return self.fail(f"No performer named '{model_type}' has weights on the floor — "
                             "check /api/stage/models for tonight's playbill.", 404)
        kind = performer["kind"]
        image = (p.get("image") or "").strip()
        start = None
        if image:
            start = (FOOTAGE / image).resolve()
            if not start.is_relative_to(FOOTAGE.resolve()) or not start.is_file():
                return self.fail(f"'{image}' is not in the footage archive.", 404)
        if kind in ("i2v", "swap") and not start:
            role = "the character to animate" if kind == "swap" else "the start image"
            return self.fail(f"{performer['name']} needs a lead — {role}. "
                             "Pick one from the footage.")
        guide = None
        if kind == "swap":
            guide = self.resolve_reel(p.get("video_guide"))
            if not guide:
                return self.fail(f"{performer['name']} is a motion-transfer performer — it needs "
                                 "a driving video (the choreography) alongside the lead.")
        loras = [str(l).strip() for l in (p.get("loras") or []) if str(l).strip()]
        if (missing := [l for l in loras if l not in performer["loras"]]):
            return self.fail(f"Not in {performer['name']}'s wardrobe (loras/{performer['lora_shelf']}/): "
                             f"{', '.join(missing)}. The playbill lists what hangs there.", 404)
        multipliers = p.get("lora_multipliers") or []
        if port_open(WAN_UI_PORT):
            return self.fail("The Wan2GP UI is holding the stage on :7860 — two performances "
                             "cannot share the GPU. Close it, then cue again.", 409)
        if not stage_lock.acquire(blocking=False):
            return self.fail("The Stage is mid-performance — one take at a time.", 409)
        try:
            if stage_job.get("state") == "running":
                return self.fail("The Stage is mid-performance — one take at a time.", 409)
            evicted = evict_llms()
            need = performer["vram_gb"]
            ok, free = clear_the_set(min_vram_gb=need)
            if not ok:
                return self.fail(
                    f"The stagehands could not clear the GPU for {performer['name']} — "
                    f"{free:.1f} GB free, {need} needed. The Face Shop is refusing to "
                    "strike its set; give it a moment and cue again, or restart ComfyUI.", 503)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            settings = dict(performer["recipe"])
            settings.update({
                # Without a current settings_version, wgp's fix_settings treats
                # the cue as ancient and rewrites video_prompt_type to the
                # model's inpaint default (whose "A" then demands a mask).
                "settings_version": 2.66,
                "model_type": model_type,
                "prompt": prompt,
                "resolution": p.get("resolution") or performer["resolution"],
                "seed": int(p.get("seed", 7)),
            })
            if kind != "t2i":
                settings["video_length"] = int(p.get("video_length") or performer["video_length"])
            if p.get("steps"):
                settings["num_inference_steps"] = int(p["steps"])
            if p.get("guidance") is not None:
                settings["guidance_scale"] = float(p["guidance"])
            if loras:
                settings["activated_loras"] = loras
                # One float per donned LoRA, space-separated — wgp's
                # parse_loras_multipliers grammar (phase syntax not exposed here).
                mults = [str(float(m)) if str(m).strip() else "1.0"
                         for m in (list(multipliers) + ["1.0"] * len(loras))[:len(loras)]]
                settings["loras_multipliers"] = " ".join(mults)
            if kind == "t2i" and start:
                # Image performers repaint: Control Image + denoising strength
                # below 1 is Wan2GP's img2img — the letter grammar demands
                # "VG" ("G" honors denoising_strength; without it wgp forces
                # 1.0), and ONLY model_mode 0 keeps the strength (the lanpaint
                # inpainting modes silently reset it — see
                # krea2_handler.normalize_lanpaint_strengths).
                settings.update({
                    "image_mode": 2,
                    "video_prompt_type": "VG",
                    "image_guide": str(start),
                    "denoising_strength": max(0.05, min(1.0, float(p.get("strength", 0.6)))),
                    "model_mode": 0,
                    "masking_strength": 1.0,
                })
            elif start:
                settings["image_start"] = str(start)
                settings["image_prompt_type"] = "S"
            elif kind == "t2v":
                settings["image_prompt_type"] = "T"
            if guide:
                settings["video_guide"] = str(guide)
            JOB_LOGS.mkdir(parents=True, exist_ok=True)
            WAN_OUT.mkdir(parents=True, exist_ok=True)
            settings_path = JOBS / f"prompter-{stamp}.json"
            settings_path.write_text(json.dumps([settings], indent=1))
            log_path = JOB_LOGS / f"prompter-{stamp}.log"
            stage_job = {"state": "running", "started": datetime.now().isoformat(timespec="seconds"),
                         "settings": settings_path.name, "log": log_path.name, "seed": settings["seed"],
                         "model": performer["name"], "kind": kind,
                         "loras": loras or None}
            threading.Thread(target=run_stage_job, args=(settings_path, log_path), daemon=True).start()
            self.reply({"state": "running", "settings": settings_path.name, "evicted": evicted})
        finally:
            stage_lock.release()

    def api_stage_cast(self, p):
        """Promote a painting into the footage archive as a Stage lead.

        Face Shop paintings by default; Krea 2 stills land in the Stage's own
        output rack, so 'from: stage' casts from there — paint with one
        performer, animate with another.
        """
        name = (p.get("image") or "").strip()
        root = WAN_OUT if p.get("from") == "stage" else COMFY_OUT
        src = (root / name).resolve()
        if not src.is_relative_to(root.resolve()) or not src.is_file():
            return self.fail("That painting is not hanging on that rack.", 404)
        shutil.copyfile(src, FOOTAGE / src.name)
        self.reply({"cast": src.name})

    # The rooms a take can be binned from. The Kiln's firings and the pack
    # queue are NOT here on purpose — they die through the Rack's own
    # verdicts (rack_discard), which keep the audit trail this window does not.
    def bin_rooms(self):
        return {"face": COMFY_OUT, "stage": WAN_OUT, "foley": MM_OUT, "footage": FOOTAGE}

    def api_take_discard(self, p):
        """Bin a take — delete one file from one of the output rooms, for good.

        The front asks behind a confirm dialog; the booth still guards: the
        room must be one of the four, the name must resolve INSIDE that room,
        and only a file goes (never a directory, never a sidecar it was not
        asked about). Nothing comes back from the bin.
        """
        room = (p.get("room") or "").strip()
        root = self.bin_rooms().get(room)
        if root is None:
            return self.fail(f"The bin takes nothing from '{room or 'nowhere'}' — only face, stage, "
                             "foley, or footage takes go in.", 404)
        name = (p.get("name") or "").strip()
        target = (root / name).resolve() if name else None
        if not target or not target.is_relative_to(root.resolve()) or not target.is_file():
            return self.fail("That take is not hanging in that room — nothing to bin.", 404)
        try:
            target.unlink()
        except OSError as e:
            return self.fail(f"The bin would not take it: {e.strerror or e}. Check the bench's disk.", 500)
        self.reply({"binned": str(target.relative_to(root.resolve())), "room": room})

    def api_stage_job(self):
        info = {k: v for k, v in stage_job.items() if k != "pid"}
        if info.get("log"):
            info["log_tail"] = tail_lines(JOB_LOGS / info["log"])
        self.reply(info)

    # -- the foley booth (MMAudio: text-to-audio + video-synced audio) ---
    def api_foley_sources(self):
        """Everything the booth can score: footage reels and fresh Stage takes."""
        def reels(root):
            if not root.exists():
                return []
            return sorted(
                str(p.relative_to(root)) for p in root.glob("**/*")
                if p.is_file() and p.suffix.lower() in (".mp4", ".webm", ".mkv")
            )
        self.reply({"footage": reels(FOOTAGE), "stage": reels(WAN_OUT)})

    def api_foley_generate(self, p):
        global foley_job
        if not MM_PY.exists():
            return self.fail("The Foley Booth is not bolted down — MMAudio/.venv is missing. "
                             "The runbook's Foley Booth section has the recipe.", 503)
        prompt = (p.get("prompt") or "").strip()
        video = (p.get("video") or "").strip()
        if not prompt and not video:
            return self.fail("The Foley Booth needs a cue (prompt), a reel to score (video), or both.")
        video_path = None
        if video:
            root = WAN_OUT if p.get("video_from") == "stage" else FOOTAGE
            video_path = (root / video).resolve()
            if not video_path.is_relative_to(root.resolve()) or not video_path.is_file():
                return self.fail(f"'{video}' is not on that shelf.", 404)
        if stage_job.get("state") == "running":
            return self.fail("The Stage is mid-performance — the GPU cannot serve two masters. "
                             "Wait for the take to finish.", 409)
        if port_open(WAN_UI_PORT):
            return self.fail("The Wan2GP UI is holding the stage on :7860 — close it, then cue again.", 409)
        if not foley_lock.acquire(blocking=False):
            return self.fail("The Foley Booth is mid-take — one score at a time.", 409)
        try:
            if foley_job.get("state") == "running":
                return self.fail("The Foley Booth is mid-take — one score at a time.", 409)
            evicted = evict_llms()
            # ~6 GB in 16-bit; 8 asked so the take never lands on a knife's edge.
            ok, free = clear_the_set(min_vram_gb=8)
            if not ok:
                return self.fail(
                    f"The stagehands could not clear the GPU for the Foley Booth — {free:.1f} GB "
                    "free, 8 needed. Give the Face Shop a moment to strike its set and cue again.", 503)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            # Per-cue output dir: MMAudio names files by prompt slug, so two seeds of the
            # SAME prompt into one dir silently overwrite (day-one scar, see the runbook).
            out_dir = MM_OUT / stamp
            out_dir.mkdir(parents=True, exist_ok=True)
            JOB_LOGS.mkdir(parents=True, exist_ok=True)
            cmd = [str(MM_PY), "demo.py",
                   "--duration", str(float(p.get("duration", 8))),
                   "--seed", str(int(p.get("seed", 7))),
                   "--negative_prompt", (p.get("negative_prompt") or "").strip(),
                   "--prompt", prompt,
                   "--output", str(out_dir)]
            if video_path:
                cmd += ["--video", str(video_path)]
            log_path = JOB_LOGS / f"foley-{stamp}.log"
            foley_job = {"state": "running", "started": datetime.now().isoformat(timespec="seconds"),
                         "out_dir": out_dir.name, "log": log_path.name, "seed": int(p.get("seed", 7)),
                         "scored": video or None}
            threading.Thread(target=run_foley_job, args=(cmd, log_path, out_dir), daemon=True).start()
            self.reply({"state": "running", "out_dir": out_dir.name, "evicted": evicted})
        finally:
            foley_lock.release()

    def api_foley_job(self):
        info = {k: v for k, v in foley_job.items() if k != "pid"}
        if info.get("log"):
            info["log_tail"] = tail_lines(JOB_LOGS / info["log"])
        self.reply(info)

    # -- the kiln room (fire a prop from a sentence) ---------------------
    def kiln_floor_is_busy(self):
        """One voiced refusal for every reason the kiln cannot light."""
        if stage_job.get("state") == "running":
            return "The Stage is mid-performance — the GPU cannot serve two masters. Wait for the take to finish."
        if foley_job.get("state") == "running":
            return "The Foley Booth is mid-take — the GPU cannot serve two masters. Wait for the score to land."
        if port_open(WAN_UI_PORT):
            return "The Wan2GP UI is holding the stage on :7860 — close it, then fire again."
        if night_shift.shift_status().get("row_id"):
            return "The Night Shift is mid-firing — the kiln serves one order at a time. Stop the shift or wait for the row."
        return None

    def api_kiln_generate(self, p):
        global kiln_job
        subject = (p.get("subject") or "").strip()
        if not subject:
            return self.fail("The kiln fires nothing from an empty subject — name the prop.")
        if (busy := self.kiln_floor_is_busy()):
            return self.fail(busy, 409)
        if not kiln_lock.acquire(blocking=False):
            return self.fail("The kiln is mid-firing — one prop at a time.", 409)
        try:
            if kiln_job.get("state") == "running":
                return self.fail("The kiln is mid-firing — one prop at a time.", 409)
            evicted = evict_llms()
            ok, free = clear_the_set(min_vram_gb=kiln.PAINT_VRAM_GB)
            if not ok:
                return self.fail(
                    f"The stagehands could not clear the GPU for the kiln — {free:.1f} GB "
                    f"free, {kiln.PAINT_VRAM_GB} needed. Give the Face Shop a moment to "
                    "strike its set and fire again.", 503)
            octree = int(p.get("octree", kiln.DEFAULT_OCTREE))
            threshold = float(p.get("threshold", kiln.DEFAULT_THRESHOLD))
            two_sided = bool(p.get("two_sided", False))
            seed = int(p["seed"]) if p.get("seed") not in (None, "") else None
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            JOB_LOGS.mkdir(parents=True, exist_ok=True)
            # kiln-*.json: a deliberate namespace break from prompter-*.json —
            # future Canisters tooling tells firings from takes without opening bodies.
            record = JOBS / f"kiln-{stamp}.json"
            record.write_text(json.dumps({"subject": subject, "octree": octree,
                                          "threshold": threshold, "two_sided": two_sided,
                                          "seed": seed}, indent=1))
            log_path = JOB_LOGS / f"kiln-{stamp}.log"

            def work(say):
                result = kiln.kiln_fire(subject, octree=octree, threshold=threshold,
                                        two_sided=two_sided, seed=seed,
                                        clear_set=clear_the_set, log=say)
                say("the turntable takes it — checking, grounding, labeling")
                kiln.appraise_candidate(result.id, clear_set=clear_the_set)
                return {"candidate": result.to_dict()}

            kiln_job = {"state": "running", "act": "fire", "subject": subject,
                        "started": datetime.now().isoformat(timespec="seconds"),
                        "settings": record.name, "log": log_path.name}
            threading.Thread(target=run_kiln_job, args=(work, log_path), daemon=True).start()
            self.reply({"state": "running", "settings": record.name, "evicted": evicted})
        finally:
            kiln_lock.release()

    def api_kiln_job(self):
        info = {k: v for k, v in kiln_job.items() if k != "pid"}
        if info.get("log"):
            info["log_tail"] = tail_lines(JOB_LOGS / info["log"])
        self.reply(info)

    # -- the curing rack (nothing ships without a thumb) -----------------
    def api_rack_list(self):
        self.reply({"candidates": kiln.rack_list()})

    def api_rack_approve(self, p):
        try:
            self.reply(kiln.rack_approve((p.get("candidate_id") or "").strip(),
                                         p.get("pack_name")))
        except kiln.RackRefusal as e:
            self.fail(str(e), 409)

    def api_rack_discard(self, p):
        try:
            self.reply(kiln.rack_discard((p.get("candidate_id") or "").strip()))
        except kiln.RackRefusal as e:
            self.fail(str(e), 409)

    # -- the prop shelf (the Workshop's own prop library) ----------------
    def api_shelf_list(self):
        self.reply({"props": kiln.shelf_list()})

    def api_rack_refire(self, p):
        global kiln_job
        candidate_id = (p.get("candidate_id") or "").strip()
        recipe = kiln.read_recipe(candidate_id)
        if recipe is None:
            return self.fail(f"No candidate '{candidate_id}' is curing on the rack.", 404)
        if (busy := self.kiln_floor_is_busy()):
            return self.fail(busy, 409)
        if not kiln_lock.acquire(blocking=False):
            return self.fail("The kiln is mid-firing — one prop at a time.", 409)
        try:
            if kiln_job.get("state") == "running":
                return self.fail("The kiln is mid-firing — one prop at a time.", 409)
            evicted = evict_llms()
            octree = int(p.get("octree", kiln.REFIRE_OCTREE))
            threshold = float(p.get("threshold", kiln.REFIRE_THRESHOLD))
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            JOB_LOGS.mkdir(parents=True, exist_ok=True)
            log_path = JOB_LOGS / f"kiln-{stamp}.log"

            def work(say):
                new_id = kiln.rack_refire(candidate_id, octree, threshold,
                                          clear_set=clear_the_set, log=say)
                say("the turntable takes the refire — checking, grounding, labeling")
                kiln.appraise_candidate(new_id, clear_set=clear_the_set)
                return {"refired": candidate_id, "candidate_id": new_id}

            kiln_job = {"state": "running", "act": "refire",
                        "subject": recipe.get("subject"),
                        "started": datetime.now().isoformat(timespec="seconds"),
                        "log": log_path.name}
            threading.Thread(target=run_kiln_job, args=(work, log_path), daemon=True).start()
            self.reply({"state": "running", "evicted": evicted})
        finally:
            kiln_lock.release()

    def api_turntable_run(self, p):
        """Manual Turntable re-run from the Rack — the same instrument the
        Kiln's shred gate uses (`turntable_qa`, via appraise_candidate)."""
        global kiln_job
        candidate_id = (p.get("candidate_id") or "").strip()
        recipe = kiln.read_recipe(candidate_id)
        if recipe is None:
            return self.fail(f"No candidate '{candidate_id}' is curing on the rack.", 404)
        if (busy := self.kiln_floor_is_busy()):
            return self.fail(busy, 409)
        if not kiln_lock.acquire(blocking=False):
            return self.fail("The kiln is mid-firing — one prop at a time.", 409)
        try:
            if kiln_job.get("state") == "running":
                return self.fail("The kiln is mid-firing — one prop at a time.", 409)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            JOB_LOGS.mkdir(parents=True, exist_ok=True)
            log_path = JOB_LOGS / f"kiln-{stamp}.log"

            def work(say):
                say(f"the turntable takes {candidate_id} for a fresh spin")
                qa = kiln.appraise_candidate(candidate_id, clear_set=clear_the_set)
                return {"candidate_id": candidate_id, "qa": qa.to_dict()}

            kiln_job = {"state": "running", "act": "appraise",
                        "subject": recipe.get("subject"),
                        "started": datetime.now().isoformat(timespec="seconds"),
                        "log": log_path.name}
            threading.Thread(target=run_kiln_job, args=(work, log_path), daemon=True).start()
            self.reply({"state": "running"})
        finally:
            kiln_lock.release()

    # -- the night shift (brief it before bed) ---------------------------
    def api_queue_list(self):
        info = {"rows": night_shift.load_queue(), "shift": night_shift.shift_status()}
        if shift_log["name"]:
            info["log_tail"] = tail_lines(JOB_LOGS / shift_log["name"])
        self.reply(info)

    def api_queue_add(self, p):
        try:
            self.reply({"row": night_shift.add_row(p.get("row") or p)})
        except night_shift.CallSheetError as e:
            self.fail(str(e))

    def api_queue_remove(self, p):
        try:
            night_shift.remove_row((p.get("row_id") or "").strip())
            self.reply({"removed": p.get("row_id")})
        except night_shift.CallSheetError as e:
            self.fail(str(e), 404)

    def api_queue_reorder(self, p):
        try:
            night_shift.reorder_row((p.get("row_id") or "").strip(),
                                    p.get("direction") or "up")
            self.reply({"rows": night_shift.load_queue()})
        except night_shift.CallSheetError as e:
            self.fail(str(e), 404)

    def api_pins_pin(self, p):
        """The Pinboard (#08) — promote a proven take's settings to a named formula."""
        try:
            self.reply({"pin": pins.pin_recipe(p.get("pin") or p)})
        except pins.PinboardError as e:
            self.fail(str(e))

    def api_pins_unpin(self, p):
        try:
            pins.unpin_recipe((p.get("pin_id") or "").strip())
            self.reply({"unpinned": p.get("pin_id")})
        except pins.PinboardError as e:
            self.fail(str(e), 404)

    def api_queue_start(self, _p):
        ok, msg = start_night_shift()
        if not ok:
            return self.fail(msg, 409)
        self.reply({"state": "running", "message": msg})

    def api_queue_stop(self, _p):
        self.reply(night_shift.stop_shift())


def split_variants(text):
    """Split '1. ...\n2. ...' forge output into a list; fall back to whole text."""
    out, current = [], None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped[:2] in {f"{i}." for i in range(1, 10)}:
            if current:
                out.append(current.strip())
            current = stripped[2:].strip()
        elif current is not None:
            current += " " + stripped
    if current:
        out.append(current.strip())
    return out or [text]


if __name__ == "__main__":
    print(f"The Prompter's Box opens its window on http://localhost:{PORT}")
    if night_shift.has_firing_row():
        # The shift died mid-row — resume from the row's takes_done cursor,
        # never the whole queue, never a duplicate take.
        ok, msg = start_night_shift()
        print(f"A Night Shift row was mid-firing when the booth went dark — {msg.lower()}"
              if ok else f"Night Shift resume refused: {msg}")
    # Loopback only. The booth spawns subprocesses and streams footage/ —
    # "personal media (the puppeteer's own face among it). Never leaves the
    # building." A bind to 0.0.0.0 handed that archive to the Windows host
    # and to whatever the firewall's inbound posture allows behind it.
    ThreadingHTTPServer((HOUSE_HOST, PORT), BoothWindow).serve_forever()
