#!/usr/bin/env python3
"""The Stagehands — the crew that clears the stage before anyone performs.

One GPU, one performance: every instrument in the booth that wants VRAM asks
the stagehands first. This module is the crew's single muster point — the
fail-closed guard (`clear_the_set`), the LLM eviction, and the driver-truth
VRAM meter — extracted from server.py so the Kiln, the Turntable, and the
Night Shift can route through the SAME guard the Forge, Face Shop, Stage,
and Foley already use. One guard, many callers, zero copies to drift.

Never weaken the guard to best-effort — proceeding anyway is the exact
stampede that OOM-killed the 31 GB WSL VM twice on 2026-07-09 and took the
GPU bridge (dxg) down with it. See the runbook, §The Stagehands' Guard.

Stdlib only, same philosophy as the rest of the booth.
"""

import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # video-lab/
COMFY_OUT = BASE / "ComfyUI" / "output"
COMFY_IN = BASE / "ComfyUI" / "input"

OLLAMA = "http://localhost:11434"
COMFY = "http://localhost:8188"
WAN_UI_PORT = 7860


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


def clear_the_set(min_vram_gb, wait_s=90):
    """Ask ComfyUI to strike its set, then VERIFY the GPU is actually clear.

    Returns (ok, vram_free_gb). FAIL-CLOSED by design: callers must refuse
    the cue when ok is False. Proceeding anyway makes Ollama offload ~10 GB
    into system RAM on top of ComfyUI's ~21 GB weight cache — that exact
    stampede OOM-killed the 31 GB WSL VM twice on 2026-07-09 and took the
    GPU bridge (dxg) down with it.

    wait_s is 90, not 30: WSL2's dxg bridge releases VRAM lazily — on the
    first live Kiln firing (2026-07-19) Klein's strike completed somewhere
    between 30 and ~90 s after /free, and the 30 s guard refused a mesh
    stage the GPU was about to be ready for. Patience is not weakness:
    the guard still refuses when the set genuinely will not strike.
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
