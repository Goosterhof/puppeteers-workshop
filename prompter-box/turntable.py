#!/usr/bin/env python3
"""The Turntable — one instrument, two consumers.

Every mesh the Kiln fires gets set on the turntable: eight deterministic
headless renders (pyrender offscreen via EGL — no display, no browser),
then three numeric geometry checks against the silhouettes and the mesh
itself. The silhouette-continuity check IS the Kiln's shredding detector —
`kiln.detect_shredding` calls the same `turntable_qa` this module exposes
to the Rack, so the two verdicts can never drift apart.

A qwen3-vl grounding pass rides along as a second opinion, never the gate:
a QAResult can fail on deterministic grounds alone and pass with the vision
model dissenting — logged, not blocking. Whatever the model says while
grounding also becomes the candidate's Canister label (the surviving half
of the Appraiser merge): a 1,246-prop archive searchable by meaning.

Not stdlib: numpy + PIL + scipy (the Keymaster's exception, extended) plus
trimesh + pyrender — the Workshop's first Python mesh tooling, recorded in
requirements.txt. pyrender imports lazily so the fixture-driven containment
suite runs without a GPU or an EGL context.
"""

import base64
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from stagehands import OLLAMA, http_json

N_ANGLES = 8
FRAME_SIZE = 512
VISION_MODEL = "qwen3-vl:8b"   # the Promptsmith's house vision voice
VISION_VRAM_GB = 8             # featherweight — same clearance the forge asks

# The three deterministic limits. Numeric, reproducible, and deliberately
# tuned so the decisive signal is silhouette continuity — the exact check
# that would have screamed "shredded spokes" in the 05½ campaign.
SILHOUETTE_HOLE_LIMIT = 0.20   # interior see-through area / silhouette area
VOXEL_OCCUPANCY_FLOOR = 0.02   # filled volume / bbox volume — lattice tatters read near-zero
ISLAND_AREA_FLOOR = 0.02       # a fragment below 2% of total surface is noise, not a part


@dataclass
class QAResult:
    """The turntable's full report — a boolean at the Kiln's gate, a card at the Rack."""
    passed: bool
    checks: dict                 # name -> {"score", "limit", "passed"}
    failure_reason: str          # voiced; names the failing check specifically
    frames: list = field(default_factory=list)   # rendered frame paths (str)
    canister_label: str | None = None            # written by the vision pass
    vision: dict | None = None                   # parsed grounding verdict — logged, never gating

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------- rendering

def _yaw_pose(angle, radius):
    return np.array([
        [math.cos(angle), 0, math.sin(angle), radius * math.sin(angle)],
        [0, 1, 0, 0],
        [-math.sin(angle), 0, math.cos(angle), radius * math.cos(angle)],
        [0, 0, 0, 1],
    ])


def render_turntable(glb_path, n_angles=N_ANGLES, out_dir=None, size=FRAME_SIZE):
    """Eight deterministic RGBA frames of a GLB, headless, no display attached.

    Renderer decision (experiment log #00062, Phase 3A): pyrender offscreen
    via EGL — it stays inside the booth's own Python process, and the same
    trimesh load feeds the voxel and island checks. One render pass feeds
    BOTH the QA checks and the Rack's preview strip: frames already on disk
    and newer than the GLB are reused, never re-drawn.
    """
    glb_path = Path(glb_path)
    out_dir = Path(out_dir) if out_dir else glb_path.parent / "turn"
    existing = sorted(out_dir.glob("*.png"))
    if len(existing) == n_angles and all(
        p.stat().st_mtime >= glb_path.stat().st_mtime for p in existing
    ):
        return existing  # one render pass, two consumers — the strip is fresh

    os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
    import trimesh
    import pyrender  # lazy: the containment suite never needs an EGL context

    mesh = trimesh.load(str(glb_path), force="mesh")
    scene = pyrender.Scene(bg_color=[0, 0, 0, 0], ambient_light=[0.55, 0.55, 0.55])
    scene.add(pyrender.Mesh.from_trimesh(mesh, smooth=False))
    scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=2.5))
    # Orthographic and centered — the silhouette is the datum, not the drama.
    span = float(np.max(mesh.extents)) if np.max(mesh.extents) > 0 else 1.0
    center = mesh.bounds.mean(axis=0)
    mag = span * 0.72
    cam = pyrender.OrthographicCamera(xmag=mag, ymag=mag, znear=0.05, zfar=span * 8)
    cam_node = scene.add(cam)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    renderer = pyrender.OffscreenRenderer(size, size)
    try:
        for i in range(n_angles):
            pose = _yaw_pose(2 * math.pi * i / n_angles, span * 2.5)
            pose[:3, 3] += center
            scene.set_pose(cam_node, pose)
            color, _ = renderer.render(scene, flags=pyrender.RenderFlags.RGBA)
            frame = out_dir / f"{i:03d}.png"
            Image.fromarray(color, "RGBA").save(frame)
            frames.append(frame)
    finally:
        renderer.delete()
    return frames


# ------------------------------------------------------- deterministic checks

def check_silhouette_continuity(frames, expected_parts=1):
    """The check the memory file names directly: shredded spokes produce a
    silhouette riddled with see-through gaps and broken into tatters.

    Per angle: the alpha silhouette must hold together — no more significant
    connected pieces than the subject legitimately has, and no gaping
    interior holes. Returns numeric worst-angle scores.
    """
    worst_parts, worst_holes = 0, 0.0
    for frame in frames:
        alpha = np.asarray(Image.open(frame).convert("RGBA"))[..., 3]
        fg = alpha > 8
        total = int(fg.sum())
        if not total:
            worst_parts = max(worst_parts, 0)
            continue
        labels, count = ndimage.label(fg)
        if count:
            sizes = ndimage.sum_labels(np.ones_like(labels), labels,
                                       index=np.arange(1, count + 1))
            significant = int((sizes >= max(24, 0.005 * total)).sum())
        else:
            significant = 0
        # interior holes: background pockets that never reach the frame border
        bg_labels, bg_count = ndimage.label(~fg)
        border = np.unique(np.concatenate([
            bg_labels[0], bg_labels[-1], bg_labels[:, 0], bg_labels[:, -1]]))
        hole_area = 0
        for lbl in range(1, bg_count + 1):
            if lbl not in border:
                hole_area += int((bg_labels == lbl).sum())
        worst_parts = max(worst_parts, significant)
        worst_holes = max(worst_holes, hole_area / (total + hole_area))
    passed = worst_parts <= expected_parts and worst_holes <= SILHOUETTE_HOLE_LIMIT
    return {
        "score": {"parts": worst_parts, "hole_ratio": round(worst_holes, 4)},
        "limit": {"parts": expected_parts, "hole_ratio": SILHOUETTE_HOLE_LIMIT},
        "passed": passed,
    }


def check_voxel_hole_ratio(mesh):
    """Interior voxel occupancy vs. the mesh's own bounding volume — a
    lattice-shredded mesh reads as mostly-empty relative to its bbox."""
    span = float(np.max(mesh.extents))
    if span <= 0:
        return {"score": 0.0, "limit": VOXEL_OCCUPANCY_FLOOR, "passed": False}
    pitch = span / 48
    try:
        vox = mesh.voxelized(pitch=pitch)
        filled = vox.fill()
        occupancy = float(filled.filled_count * pitch ** 3 / np.prod(mesh.extents))
    except Exception:
        occupancy = 0.0  # a mesh the voxelizer cannot even grid is not a prop
    return {
        "score": round(occupancy, 4),
        "limit": VOXEL_OCCUPANCY_FLOOR,
        "passed": occupancy >= VOXEL_OCCUPANCY_FLOOR,
    }


def check_floating_islands(mesh, expected_parts=1):
    """Disconnected fragments with no path to the main body. A prop should be
    one object — occasionally two, for genuinely separate parts, declared via
    expected_parts rather than silently guessed."""
    parts = mesh.split(only_watertight=False)
    if len(parts) == 0:
        return {"score": 0, "limit": expected_parts, "passed": False}
    total_area = sum(float(p.area) for p in parts) or 1.0
    significant = sum(1 for p in parts if float(p.area) / total_area >= ISLAND_AREA_FLOOR)
    return {
        "score": int(significant),
        "limit": expected_parts,
        "passed": significant <= expected_parts,
    }


# ------------------------------------------------------------- vision pass

GROUNDING_PROMPT = (
    "You are grounding a rendered 3D prop for a theatre workshop's kiln.\n"
    "Look at the render and answer in EXACTLY three lines, nothing else:\n"
    "RECOGNIZED: yes or no — is this recognizably {subject}?\n"
    "BROKEN: yes or no — are parts obviously missing, shredded, or broken?\n"
    "LABEL: a short one-line description of the object (subject, pose, material)."
)


def parse_grounding_reply(text):
    """Parse the three-line grounding reply defensively — qwen3 may wrap it
    in thinking blocks or add flourish; the parse survives both."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    parsed = {"recognized": None, "broken": None, "label": None}
    for line in text.splitlines():
        line = line.strip().strip("*").strip()
        m = re.match(r"(?i)^(recognized|broken|label)\s*:\s*(.+)$", line)
        if not m:
            continue
        key, value = m.group(1).lower(), m.group(2).strip()
        if key == "label":
            parsed["label"] = parsed["label"] or value
        else:
            verdict = re.match(r"(?i)^(yes|no)\b", value)
            if verdict and parsed[key] is None:
                parsed[key] = verdict.group(1).lower() == "yes"
    return parsed


def vision_ground(frame_path, subject_phrase, model=VISION_MODEL):
    """One rendered angle in front of qwen3-vl: is it the subject, is it
    whole, and what should the Canister call it. Caller guards the GPU —
    `turntable_qa` runs `clear_set` before this call, always."""
    image_b64 = base64.b64encode(Path(frame_path).read_bytes()).decode()
    reply = http_json(f"{OLLAMA}/api/generate", {
        "model": model,
        "prompt": GROUNDING_PROMPT.format(subject=subject_phrase),
        "images": [image_b64],
        "stream": False,
        "think": False,
    }, timeout=180)
    return parse_grounding_reply(reply.get("response", ""))


# --------------------------------------------------------------- the verdict

def turntable_qa(glb_path, expected_parts=1, subject_phrase=None,
                 out_dir=None, clear_set=None):
    """Set a mesh on the turntable and return the full QAResult.

    This is the ONE instrument: `kiln.detect_shredding` calls it for the
    auto-refire gate (deterministic only), the booth's `api_turntable_run`
    calls it for the Rack card (with the vision pass riding along when a
    subject phrase and a stage guard are handed in).

    The gate is numeric: `passed` is decided by the three deterministic
    checks alone. The vision pass can dissent in the report; it cannot veto.
    """
    import trimesh  # lazy, mirrors render_turntable

    glb_path = Path(glb_path)
    frames = render_turntable(glb_path, out_dir=out_dir)
    mesh = trimesh.load(str(glb_path), force="mesh")

    checks = {
        "silhouette_continuity": check_silhouette_continuity(frames, expected_parts),
        "voxel_hole_ratio": check_voxel_hole_ratio(mesh),
        "floating_islands": check_floating_islands(mesh, expected_parts),
    }
    passed = all(c["passed"] for c in checks.values())

    reasons = []
    if not checks["silhouette_continuity"]["passed"]:
        s = checks["silhouette_continuity"]["score"]
        reasons.append(
            "silhouette continuity failed — the outline breaks into "
            f"{s['parts']} pieces (expected {expected_parts}) with "
            f"{s['hole_ratio']:.0%} see-through gaps on the turn"
        )
    if not checks["voxel_hole_ratio"]["passed"]:
        reasons.append(
            "voxel-hole ratio failed — the body is "
            f"{checks['voxel_hole_ratio']['score']:.1%} material against its own "
            "bounding volume; lattice tatters, not a prop"
        )
    if not checks["floating_islands"]["passed"]:
        reasons.append(
            f"floating islands failed — {checks['floating_islands']['score']} "
            f"disconnected fragments where {expected_parts} body was expected"
        )

    vision = None
    label = None
    if subject_phrase and clear_set is not None:
        # The guard fires at the swap boundary, not once at the door —
        # qwen3-vl never loads against a resident mesh model.
        ok, _free = clear_set(VISION_VRAM_GB)
        if ok:
            try:
                vision = vision_ground(frames[0], subject_phrase)
                label = vision.get("label")
            except OSError:
                vision = {"error": "the appraiser never answered — Ollama is dark on :11434"}
        else:
            vision = {"error": "the stagehands could not clear the GPU for the appraiser"}

    return QAResult(
        passed=passed,
        checks=checks,
        failure_reason="; ".join(reasons),
        frames=[str(f) for f in frames],
        canister_label=label,
        vision=vision,
    )


def write_qa(candidate_dir, qa):
    """File the turntable's report beside the candidate's recipe."""
    path = Path(candidate_dir) / "qa.json"
    path.write_text(json.dumps(qa.to_dict(), indent=1))
    return path
