#!/usr/bin/env python3
"""The Prompter's Box — the booth that feeds lines to the performers.

One console on http://localhost:7900 for the whole workshop pipeline:
forge prompts (The Promptsmith / qwen3:14b), fire them at the Face Shop
(ComfyUI Flux 2 Klein, headless) or the Stage (Wan2GP headless --process),
and watch the results — with VRAM choreography handled for you.

Stdlib only, same philosophy as the Promptsmith: no venv, no dependencies.
"""

import json
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # video-lab/
STATIC = Path(__file__).resolve().parent / "static"
FOOTAGE = BASE / "footage"
JOBS = BASE / "jobs"
JOB_LOGS = JOBS / "logs"
WAN_DIR = BASE / "Wan2GP"
WAN_PY = WAN_DIR / ".venv" / "bin" / "python"
WAN_OUT = WAN_DIR / "outputs"
WAN_DEFAULTS = WAN_DIR / "defaults"
WAN_SETTINGS = WAN_DIR / "settings"
WAN_CKPTS = WAN_DIR / "ckpts"
WAN_LORAS = WAN_DIR / "loras"
COMFY_OUT = BASE / "ComfyUI" / "output"
COMFY_PAINTERS = BASE / "ComfyUI" / "models" / "diffusion_models"
MM_DIR = BASE / "MMAudio"
MM_PY = MM_DIR / ".venv" / "bin" / "python"
MM_OUT = MM_DIR / "output" / "prompter"
FF_SHARED = BASE / "ffmpeg-shared" / "lib"  # torchcodec's substrate — see the runbook

OLLAMA = "http://localhost:11434"
COMFY = "http://localhost:8188"
WAN_UI_PORT = 7860
PORT = 7900

sys.path.insert(0, str(BASE / "prompt-forge"))
from promptsmith import DEFAULT_MODEL, FORGE_PROFILES, VISION_MODEL, forge  # noqa: E402

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

stage_lock = threading.Lock()
stage_job = {"state": "idle"}  # idle | running | done | failed

foley_lock = threading.Lock()
foley_job = {"state": "idle"}  # idle | running | done | failed


def http_json(url, payload=None, timeout=10):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"} if data else {}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body) if body.strip() else {}


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def loaded_llms():
    try:
        return http_json(f"{OLLAMA}/api/ps", timeout=2).get("models", [])
    except OSError:
        return None  # forge is cold


def evict_llms():
    """Clear the booth's own models off the GPU before a performance."""
    evicted = []
    for m in loaded_llms() or []:
        try:
            http_json(
                f"{OLLAMA}/api/generate", {"model": m["model"], "keep_alive": 0}, timeout=30
            )
            evicted.append(m["model"])
        except OSError:
            pass
    return evicted


def gpu_vram_free_gb():
    """VRAM truth straight from the driver — ComfyUI's self-report lags."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        total, used = (int(v.strip()) for v in out.stdout.strip().split(","))
        return (total - used) / 1024
    except (OSError, ValueError):
        return None


def ram_available_gb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable"):
                return int(line.split()[1]) / 1048576
    except OSError:
        pass
    return None


def clear_the_set(min_vram_gb, wait_s=30):
    """Ask ComfyUI to strike its set, then VERIFY the GPU is actually clear.

    Returns (ok, vram_free_gb). FAIL-CLOSED by design: callers must refuse
    the cue when ok is False. Proceeding anyway makes Ollama offload ~10 GB
    into system RAM on top of ComfyUI's ~21 GB weight cache — that exact
    stampede OOM-killed the 31 GB WSL VM twice on 2026-07-09 and took the
    GPU bridge (dxg) down with it.
    """
    free = gpu_vram_free_gb()
    if free is None or free >= min_vram_gb:
        return True, free
    try:
        http_json(f"{COMFY}/free", {"unload_models": True, "free_memory": True}, timeout=5)
        # The /free flags are only consumed when the prompt worker wakes from
        # q.get(timeout=1000) — idle for >10 s, that's up to 16 minutes away.
        # Knock: a 1-pixel no-op prompt wakes the worker, executes in
        # milliseconds, and the flags are read right after it completes.
        knock = {
            "1": {"class_type": "EmptyImage",
                  "inputs": {"width": 16, "height": 16, "batch_size": 1, "color": 0}},
            "2": {"class_type": "PreviewImage", "inputs": {"images": ["1", 0]}},
        }
        http_json(f"{COMFY}/prompt", {"prompt": knock}, timeout=5)
    except OSError:
        pass  # Face Shop dark — whatever holds the GPU, it is not ComfyUI
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(1)
        free = gpu_vram_free_gb()
        if free is None or free >= min_vram_gb:
            return True, free
    return False, free


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


def tail_lines(path, n=25):
    try:
        raw = Path(path).read_bytes()[-16384:].decode(errors="replace")
        lines = [l.rstrip() for l in raw.replace("\r", "\n").splitlines() if l.strip()]
        return lines[-n:]
    except OSError:
        return []


class Handler(BaseHTTPRequestHandler):
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
        path, _, query = self.path.partition("?")
        path = urllib.parse.unquote(path)
        if path in ("/", "/index.html"):
            return self.send_file(STATIC, "index.html")
        if path.startswith("/footage/"):
            return self.send_file(FOOTAGE, path[len("/footage/"):])
        if path.startswith("/face-output/"):
            return self.send_file(COMFY_OUT, path[len("/face-output/"):])
        if path.startswith("/stage-output/"):
            return self.send_file(WAN_OUT, path[len("/stage-output/"):])
        if path.startswith("/foley-output/"):
            return self.send_file(MM_OUT, path[len("/foley-output/"):])
        if path == "/api/status":
            return self.api_status()
        if path == "/api/archive":
            return self.api_archive()
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
            "/api/foley/generate": self.api_foley_generate,
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
        except (OSError, LookupError):
            comfy = {"up": False}
        self.reply({
            "forge": {"up": llms is not None,
                      "loaded": [{"model": m["model"], "size_gb": round(m.get("size", 0) / 1e9, 1)}
                                 for m in llms or []]},
            "face_shop": comfy,
            "stage_ui": {"up": port_open(WAN_UI_PORT)},
            "stage_job": {k: v for k, v in stage_job.items() if k != "pid"},
            "foley": {"installed": MM_PY.exists(),
                      "job_state": foley_job.get("state", "idle")},
        })

    def api_archive(self):
        """The racks — every previous take still hanging in the output rooms.

        The booth itself is stateless between page loads; the racks let the
        UI show history straight from the filesystem, newest first.
        """
        def rack(root, exts, recurse=False, limit=150):
            if not root.exists():
                return []
            items = []
            for p in (root.glob("**/*") if recurse else root.iterdir()):
                if p.is_file() and p.suffix.lower() in exts:
                    kind = ("image" if p.suffix.lower() in IMAGE_EXTS
                            else "audio" if p.suffix.lower() == ".flac" else "video")
                    items.append({"name": str(p.relative_to(root)),
                                  "mtime": int(p.stat().st_mtime), "kind": kind})
            items.sort(key=lambda x: -x["mtime"])
            return items[:limit]
        self.reply({
            "stage": rack(WAN_OUT, VIDEO_EXTS + IMAGE_EXTS),
            "face": rack(COMFY_OUT, IMAGE_EXTS),
            "foley": rack(MM_OUT, (".flac", ".mp4"), recurse=True),
        })

    def api_footage(self):
        images = sorted(p.name for p in FOOTAGE.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
        self.reply({"images": images})

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
        if stage_job.get("state") == "running":
            return self.fail("The Stage is mid-performance — the GPU cannot serve two masters. "
                             "Wait for the take to finish.", 409)
        evicted = evict_llms()
        # Unique prefix per cue: an exact repeat (same prompt+seed) would otherwise
        # be fully served from ComfyUI's cache — SaveImage skipped, no file, and the
        # take looks failed. A fresh prefix forces SaveImage to run (instant, cached
        # tensor) so every cue lands an image.
        stamp = datetime.now().strftime("%H%M%S")
        graph = klein_graph(prompt, int(p.get("width", 768)), int(p.get("height", 1024)),
                            int(p.get("seed", int(time.time()) % 2**31)), int(p.get("steps", 4)),
                            prefix=f"PrompterBox-{stamp}", painter=painter)
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
            if start:
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
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
