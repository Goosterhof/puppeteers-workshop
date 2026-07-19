"""Fixtures for the Kiln Room's containment suite — fixture-driven, no GPU.

The real turntable renders through pyrender + EGL on the bench (spiked and
proven before any check function was written); this suite substitutes a
deterministic pure-software orthographic rasterizer so every check runs
without hardware. The check functions consume frames and never know who
drew them — the exact substitution seam the experiment log designed.
"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image, ImageDraw

BOOTH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BOOTH))


def software_turntable(glb_path, n_angles=8, out_dir=None, size=256):
    """Orthographic silhouette rasterizer — the same framing contract as
    turntable.render_turntable (yaw loop, xmag = span * 0.72), drawn with
    PIL instead of OpenGL. Deterministic by construction."""
    glb_path = Path(glb_path)
    out_dir = Path(out_dir) if out_dir else glb_path.parent / "turn"
    out_dir.mkdir(parents=True, exist_ok=True)
    mesh = trimesh.load(str(glb_path), force="mesh")
    center = mesh.bounds.mean(axis=0)
    span = float(np.max(mesh.extents)) or 1.0
    mag = span * 0.72
    scale = size / (2 * mag)
    verts = mesh.vertices - center
    frames = []
    for i in range(n_angles):
        a = 2 * math.pi * i / n_angles
        # camera yawed by a == mesh yawed by -a; project onto view XY
        x = verts[:, 0] * math.cos(a) - verts[:, 2] * math.sin(a)
        y = verts[:, 1]
        px = x * scale + size / 2
        py = size / 2 - y * scale
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        for face in mesh.faces:
            draw.polygon([(px[v], py[v]) for v in face], fill=255)
        rgba = Image.merge("RGBA", (mask, mask, mask, mask))
        frame = out_dir / f"{i:03d}.png"
        rgba.save(frame)
        frames.append(frame)
    return frames


@pytest.fixture
def software_render(monkeypatch):
    """Swap the EGL renderer for the software rasterizer, suite-wide seam."""
    import turntable
    monkeypatch.setattr(turntable, "render_turntable", software_turntable)
    return software_turntable


@pytest.fixture
def solid_glb(tmp_path):
    """The gnome stand-in: one solid, chunky, connected body."""
    path = tmp_path / "solid.glb"
    trimesh.creation.box(extents=(1.0, 1.2, 0.8)).export(path)
    return path


@pytest.fixture
def shredded_wheel_glb(tmp_path):
    """The omafiets stand-in at octree 128: a spoked wheel shredded into
    see-through tatters — twelve disconnected fragments on a ring."""
    path = tmp_path / "shredded.glb"
    fragments = []
    for i in range(12):
        a = 2 * math.pi * i / 12
        frag = trimesh.creation.box(extents=(0.16, 0.08, 0.02))
        frag.apply_translation((math.cos(a), math.sin(a), 0))
        fragments.append(frag)
    trimesh.util.concatenate(fragments).export(path)
    return path


@pytest.fixture
def healed_wheel_glb(tmp_path):
    """The same wheel after the 224/0.4 refire: one connected disk."""
    path = tmp_path / "healed.glb"
    trimesh.creation.cylinder(radius=1.0, height=0.08, sections=48).export(path)
    return path


@pytest.fixture
def kiln_sandbox(tmp_path, monkeypatch):
    """Redirect the Kiln's write boundary and the pack queue into a sandbox."""
    import kiln
    out = tmp_path / "kiln-output"
    queue = tmp_path / "pack-queue"
    monkeypatch.setattr(kiln, "KILN_OUT", out)
    monkeypatch.setattr(kiln, "PACK_QUEUE", queue)
    return {"out": out, "queue": queue}


def paint_fixture(path, size=200, box=(60, 60, 140, 140), key=(255, 0, 255)):
    """A Klein prop-shot stand-in: chroma ground, one dark subject block,
    with a rim of gate-matching lavender spill on the subject's edge."""
    img = np.zeros((size, size, 3), dtype=np.uint8)
    img[...] = key
    x0, y0, x1, y1 = box
    img[y0:y1, x0:x1] = (30, 30, 30)                 # the dark frame tubes
    img[y0:y0 + 3, x0:x1] = (120, 60, 120)           # lavender key spill — gate bait
    Image.fromarray(img, "RGB").save(path)
    return path
