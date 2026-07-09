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
COMFY_OUT = BASE / "ComfyUI" / "output"

OLLAMA = "http://localhost:11434"
COMFY = "http://localhost:8188"
WAN_UI_PORT = 7860
PORT = 7900

sys.path.insert(0, str(BASE / "prompt-forge"))
from promptsmith import DEFAULT_MODEL, FORGE_PROFILES, VISION_MODEL, forge  # noqa: E402

# The arc-proven Wan 2.2 i2v Enhanced Lightning recipe (jobs/crier-bell-14b.json)
WAN_RECIPE = {
    "model_type": "i2v_2_2_Enhanced_Lightning_v2",
    "image_prompt_type": "S",
    "num_inference_steps": 4,
    "guidance_phases": 2,
    "switch_threshold": 900,
    "guidance_scale": 1,
    "guidance2_scale": 1,
    "flow_shift": 5,
}

stage_lock = threading.Lock()
stage_job = {"state": "idle"}  # idle | running | done | failed


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


def klein_graph(prompt, width, height, seed, steps, prefix="PrompterBox"):
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux-2-klein-9b-BF16.gguf"}},
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
    videos = [n for n in new if n.lower().endswith((".mp4", ".webm", ".mkv"))]
    stage_job.update(
        {
            "state": "done" if code == 0 and videos else "failed",
            "exit_code": code,
            "outputs": videos or new,
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
        if path == "/api/status":
            return self.api_status()
        if path == "/api/footage":
            return self.api_footage()
        if path == "/api/stage/job":
            return self.api_stage_job()
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

    def api_face_generate(self, p):
        prompt = (p.get("prompt") or "").strip()
        if not prompt:
            return self.fail("The Face Shop paints nothing from an empty cue.")
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
                            prefix=f"PrompterBox-{stamp}")
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

    def api_stage_generate(self, p):
        global stage_job
        prompt, image = (p.get("prompt") or "").strip(), (p.get("image") or "").strip()
        if not prompt or not image:
            return self.fail("The Stage needs both a cue (prompt) and a lead (start image).")
        start = (FOOTAGE / image).resolve()
        if not start.is_relative_to(FOOTAGE.resolve()) or not start.is_file():
            return self.fail(f"'{image}' is not in the footage archive.", 404)
        if port_open(WAN_UI_PORT):
            return self.fail("The Wan2GP UI is holding the stage on :7860 — two performances "
                             "cannot share the GPU. Close it, then cue again.", 409)
        if not stage_lock.acquire(blocking=False):
            return self.fail("The Stage is mid-performance — one take at a time.", 409)
        try:
            if stage_job.get("state") == "running":
                return self.fail("The Stage is mid-performance — one take at a time.", 409)
            evicted = evict_llms()
            ok, free = clear_the_set(min_vram_gb=26)
            if not ok:
                return self.fail(
                    f"The stagehands could not clear the GPU for the Stage — {free:.1f} GB "
                    "free, 26 needed for the 14B performance. The Face Shop is refusing to "
                    "strike its set; give it a moment and cue again, or restart ComfyUI.", 503)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            settings = dict(WAN_RECIPE)
            settings.update({
                "prompt": prompt, "image_start": str(start),
                "resolution": p.get("resolution", "704x1280"),
                "video_length": int(p.get("video_length", 41)),
                "seed": int(p.get("seed", 7)),
            })
            JOB_LOGS.mkdir(parents=True, exist_ok=True)
            WAN_OUT.mkdir(parents=True, exist_ok=True)
            settings_path = JOBS / f"prompter-{stamp}.json"
            settings_path.write_text(json.dumps([settings], indent=1))
            log_path = JOB_LOGS / f"prompter-{stamp}.log"
            stage_job = {"state": "running", "started": datetime.now().isoformat(timespec="seconds"),
                         "settings": settings_path.name, "log": log_path.name, "seed": settings["seed"]}
            threading.Thread(target=run_stage_job, args=(settings_path, log_path), daemon=True).start()
            self.reply({"state": "running", "settings": settings_path.name, "evicted": evicted})
        finally:
            stage_lock.release()

    def api_stage_cast(self, p):
        """Promote a Face Shop painting into the footage archive as a Stage lead."""
        name = (p.get("image") or "").strip()
        src = (COMFY_OUT / name).resolve()
        if not src.is_relative_to(COMFY_OUT.resolve()) or not src.is_file():
            return self.fail("That painting is not hanging in the Face Shop.", 404)
        shutil.copyfile(src, FOOTAGE / src.name)
        self.reply({"cast": src.name})

    def api_stage_job(self):
        info = {k: v for k, v in stage_job.items() if k != "pid"}
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
