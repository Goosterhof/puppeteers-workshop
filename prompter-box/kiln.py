#!/usr/bin/env python3
"""The Kiln — a prop is a sentence, not a checklist.

The eight hand-run steps of a town-sketches prop firing, wired into one
chain: Klein paints the subject on a chroma ground, the Keymaster's
border-connected gate keys it clean (border-alpha == 0 or the firing is
refused), the purple-gated despill catches what plain despill misses on
dark tubes, the hide is cropped to its alpha bbox +6 px, Hunyuan3D fires
the mesh, and the Turntable judges the result before a human ever sees it.
A thin structure that shreds at octree 128 is refired ONCE at 224/0.4 —
the memory file's own numbers — and never a second time: a mesh that still
shreds after the known cure is a novel failure, and novel failures belong
to the Scientist, not to a loop guessing blind.

Every default and gate here is a citation, not an invention — ported from
`.claude/memory/ai-video-generation.md` §The Kiln Dresses Its Props (the
lab archive's canonical section) via experiment log #00062.

Nothing this module fires ever reaches the pack queue on its own: firings
land in `kiln-output/` as `status: pending` candidates on the Curing Rack,
and only an explicit `rack_approve` — a Scientist's thumb — moves a prop
into `pack-queue/`. The machine fires; the human still judges.

Not stdlib: numpy + PIL + scipy (the Keymaster's exception, extended) —
see requirements.txt and the runbook.
"""

import json
import shutil
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image
from scipy import ndimage

import stagehands
from stagehands import COMFY, COMFY_IN, COMFY_OUT, http_json
from turntable import turntable_qa, write_qa

KILN_DIR = Path(__file__).resolve().parent
KILN_OUT = KILN_DIR / "kiln-output"          # candidates cure here — never auto-shipped
PACK_QUEUE = KILN_DIR / "pack-queue"         # only rack_approve may write here
PACK_NAME_RE = re.compile(r"^[a-z0-9-]+$")   # pack-props.mjs's own filename law

HUNYUAN_CKPT = "hunyuan_3d_v2.1.safetensors"
DEFAULT_OCTREE = 128
DEFAULT_THRESHOLD = 0.5
REFIRE_OCTREE = 224        # the known cure for the known failure (thin structures)
REFIRE_THRESHOLD = 0.4     # softer threshold keeps thin features as material
ALPHA_BBOX_PAD = 6         # the +6 px crop law — uncropped hides dress props in magenta
KEY_TOLERANCE = 20.0       # the Keymaster's own chroma distance
KEY_MIN_ISLAND = 3000      # enclosed pockets of true ground (inside an arm akimbo)
BORDER_RING = 10
VIGNETTE_CROP = 14         # Klein stills wear a ~14 px darker edge vignette that
                           # survives chroma-distance keying — crop it FIRST
                           # (the Menagerie's own law, comfyui-wangp-ops 2026-07-10;
                           # first live firing refused at border alpha 451605
                           # until this was ported)

MESH_VRAM_GB = 10          # Hunyuan3D 2.1 all-in-one is 7.4 GB — asked with margin
PAINT_VRAM_GB = 12         # Klein 9B GGUF + encoder/VAE clearance at the door


class KilnColdError(RuntimeError):
    """Infrastructure failure — the kiln itself went dark, not the prop."""


class KilnRefusal(RuntimeError):
    """A gate failed closed — the firing is refused, never shipped broken."""


class RackRefusal(RuntimeError):
    """The Rack declines an action, with the reason voiced."""


@dataclass
class KilnResult:
    """One firing's full account — what was fired, how, and with what scars."""
    id: str
    subject: str
    glb_path: str
    hide_path: str
    back_path: str | None
    octree: int
    threshold: float
    seed: int
    refire_count: int
    shredding_detected: bool     # True only if it STILL tatters after the cure
    orient_hint: str
    two_sided: bool

    def to_dict(self):
        return asdict(self)


# ------------------------------------------------------------- palette laws

GREEN_PALETTE = ("green", "leaf", "leaves", "foliage", "grass", "plant",
                 "geranium", "hedge", "ivy", "moss", "fern")
MAGENTA_PALETTE = ("magenta", "pink", "purple", "violet", "lavender", "fuchsia")


def pick_key_colour(subject):
    """Key colour disjoint from the subject's own palette — the reconfirmed
    Klein prop-shot rule. Magenta is the house ground (Decision 022's proven
    kiln recipe); a subject wearing magenta's own family sends the key to
    green, and a subject wearing both families sends it to blue."""
    words = subject.lower()
    holds_green = any(w in words for w in GREEN_PALETTE)
    holds_magenta = any(w in words for w in MAGENTA_PALETTE)
    if holds_magenta and holds_green:
        return "chroma blue", "#0000FF"
    if holds_magenta:
        return "chroma green", "#00FF00"
    return "chroma magenta", "#FF00FF"


def kiln_prop_prompt(subject, key_name, key_hex):
    return (
        f"a single {subject}, the only object in the frame, centered with clear "
        f"margin on every side, full subject visible, on a completely flat solid "
        f"{key_name} background ({key_hex}), even lighting, no shadow cast on the "
        "background, no text, no watermark"
    )


BACK_PROMPT = (
    "the exact same {subject} seen directly from behind, identical object, "
    "identical colors and materials, same flat solid {key_name} background "
    "({key_hex}), even lighting, no shadow on the background"
)


def kiln_paint_graph(subject, seed, prefix, painter=None, size=1024):
    """The Klein API graph for a prop-shot: chroma ground, single subject
    centered, palette-disjoint key colour. Rides the Face Shop's own easel
    (klein_graph) rather than duplicating the node topology."""
    from server import DEFAULT_PAINTER, klein_graph  # at call time server is whole
    key_name, key_hex = pick_key_colour(subject)
    return klein_graph(
        kiln_prop_prompt(subject, key_name, key_hex),
        size, size, seed, steps=4, prefix=prefix,
        painter=painter or DEFAULT_PAINTER,
    )


def kiln_back_graph(subject, seed, prefix, source_name, painter=None):
    """The identity-anchored ReferenceLatent EDIT graph for the far side of an
    asymmetric subject — ported from the memory file's gnome case."""
    from server import DEFAULT_PAINTER, klein_edit_graph
    key_name, key_hex = pick_key_colour(subject)
    return klein_edit_graph(
        BACK_PROMPT.format(subject=subject, key_name=key_name, key_hex=key_hex),
        seed, steps=4, prefix=prefix,
        painter=painter or DEFAULT_PAINTER, source_name=source_name,
    )


def kiln_mesh_graph(image_name, octree, threshold, seed, prefix):
    """The Hunyuan3D 2.1 firing graph, per the runbook's model table:
    ImageOnlyCheckpointLoader → CLIPVisionEncode → Hunyuan3Dv2Conditioning →
    KSampler 30 steps cfg 5 → VAEDecodeHunyuan3D → VoxelToMesh 'surface net'
    → SaveGLB. Octree rides the VAE decode; threshold rides VoxelToMesh."""
    return {
        "ckpt": {"class_type": "ImageOnlyCheckpointLoader",
                 "inputs": {"ckpt_name": HUNYUAN_CKPT}},
        "load": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "enc": {"class_type": "CLIPVisionEncode",
                "inputs": {"clip_vision": ["ckpt", 1], "image": ["load", 0],
                           "crop": "center"}},
        "cond": {"class_type": "Hunyuan3Dv2Conditioning",
                 "inputs": {"clip_vision_output": ["enc", 0]}},
        "latent": {"class_type": "EmptyLatentHunyuan3Dv2",
                   "inputs": {"resolution": 3072, "batch_size": 1}},
        "ks": {"class_type": "KSampler",
               "inputs": {"model": ["ckpt", 0], "positive": ["cond", 0],
                          "negative": ["cond", 1], "latent_image": ["latent", 0],
                          "seed": seed, "steps": 30, "cfg": 5.0,
                          "sampler_name": "euler", "scheduler": "normal",
                          "denoise": 1.0}},
        "vox": {"class_type": "VAEDecodeHunyuan3D",
                "inputs": {"samples": ["ks", 0], "vae": ["ckpt", 2],
                           "num_chunks": 8000, "octree_resolution": octree}},
        "mesh": {"class_type": "VoxelToMesh",
                 "inputs": {"voxel": ["vox", 0], "algorithm": "surface net",
                            "threshold": threshold}},
        "save": {"class_type": "SaveGLB",
                 "inputs": {"mesh": ["mesh", 0], "filename_prefix": f"3D/{prefix}"}},
    }


# --------------------------------------------------------- ComfyUI plumbing

def _submit_and_wait(graph, timeout_s=600):
    """Post a graph to ComfyUI and wait for its history entry. Returns the
    list of output file paths under ComfyUI/output. Fails voiced and closed."""
    try:
        res = http_json(f"{COMFY}/prompt", {"prompt": graph}, timeout=15)
    except OSError as e:
        raise KilnColdError(
            "The kiln went cold — ComfyUI is not answering on :8188. "
            "Raise it with ./start-comfyui.sh, then fire again."
        ) from e
    prompt_id = res["prompt_id"]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(1.5)
        try:
            hist = http_json(f"{COMFY}/history/{urllib.parse.quote(prompt_id)}", timeout=10)
        except OSError as e:
            raise KilnColdError(
                "The kiln went cold mid-firing — ComfyUI stopped answering on :8188."
            ) from e
        if prompt_id not in hist:
            continue
        entry = hist[prompt_id]
        if entry["status"].get("status_str") == "error":
            detail = json.dumps(entry["status"].get("messages", []))[:400]
            raise KilnColdError(f"The kiln spat the firing back — ComfyUI errored: {detail}")
        paths = []
        for node_out in entry.get("outputs", {}).values():
            for entries in node_out.values():
                if not isinstance(entries, list):
                    continue
                for item in entries:
                    if isinstance(item, dict) and item.get("filename"):
                        paths.append(COMFY_OUT / item.get("subfolder", "") / item["filename"])
        return paths
    raise KilnColdError(
        f"The kiln timed out after {timeout_s}s — the firing never came out of ComfyUI."
    )


def paint_subject(subject, seed, prefix, back_of=None):
    """One Klein paint (or the identity-anchored back paint when `back_of`
    names a source already standing in ComfyUI's input room)."""
    graph = (kiln_back_graph(subject, seed, prefix, source_name=back_of)
             if back_of else kiln_paint_graph(subject, seed, prefix))
    paintings = [p for p in _submit_and_wait(graph)
                 if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    if not paintings:
        raise KilnColdError("The paint stage produced no image — ComfyUI kept the canvas.")
    return paintings[-1]


def fire_mesh(hide_path, octree=DEFAULT_OCTREE, threshold=DEFAULT_THRESHOLD,
              seed=7, prefix="KilnFire"):
    """Fire the Hunyuan3D kiln on a keyed hide; returns the GLB path in
    ComfyUI's output room. Same seed across a refire keeps the KSampler
    latent cached — only decode + mesh re-run, the refire is nearly free."""
    hide_path = Path(hide_path)
    hide_name = f"kiln-hide-{uuid4().hex[:8]}{hide_path.suffix.lower()}"
    COMFY_IN.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(hide_path, COMFY_IN / hide_name)
    graph = kiln_mesh_graph(hide_name, octree, threshold, seed, prefix)
    meshes = [p for p in _submit_and_wait(graph) if p.suffix.lower() == ".glb"]
    if not meshes:
        raise KilnColdError("The mesh stage produced no GLB — the kiln door never opened.")
    return meshes[-1]


# ----------------------------------------------------------- the image laws

def key_prop_image(png_path, tolerance=KEY_TOLERANCE, min_island=KEY_MIN_ISLAND):
    """The Keymaster's border-connected topology gate, adapted to a still:
    only regions that touch the frame border (or enclosed pockets larger
    than min_island) are keyed, so a subject's face can never be eaten.
    Border alpha must land at EXACTLY 0 after keying, or the gate fails
    closed and the firing is refused — never silently shipped translucent.

    The ~14 px edge vignette Klein paints on a still is cropped BEFORE the
    ring is sampled — vignetted corners sit ~55 chroma-distance units off
    the ring median (measured on the first live omafiets firing) and no
    honest tolerance can hold both them and the subject. The Menagerie's
    pipeline learned this on 2026-07-10; the Kiln inherits the law rather
    than widening the tolerance."""
    rgb = np.asarray(Image.open(png_path).convert("RGB"))
    if min(rgb.shape[:2]) > 4 * VIGNETTE_CROP:
        rgb = rgb[VIGNETTE_CROP:-VIGNETTE_CROP, VIGNETTE_CROP:-VIGNETTE_CROP]
    h, w, _ = rgb.shape
    ring = np.concatenate([
        rgb[:BORDER_RING].reshape(-1, 3),
        rgb[-BORDER_RING:].reshape(-1, 3),
        rgb[:, :BORDER_RING].reshape(-1, 3),
        rgb[:, -BORDER_RING:].reshape(-1, 3),
    ])
    bg = np.median(ring, axis=0)
    dist = np.sqrt(((rgb.astype(np.float32) - bg) ** 2).sum(axis=2))
    candidate = dist < tolerance
    labels, count = ndimage.label(candidate)
    if count:
        border_labels = np.unique(np.concatenate([
            labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
        sizes = ndimage.sum_labels(np.ones_like(labels), labels,
                                   index=np.arange(1, count + 1))
        keep = np.zeros(count + 1, dtype=bool)
        keep[border_labels] = True
        keep[1:][sizes >= min_island] = True
        keep[0] = False
        keyed = keep[labels]
    else:
        keyed = candidate
    alpha = np.where(keyed, 0, 255).astype(np.uint8)
    border_alpha = int(alpha[0].sum() + alpha[-1].sum()
                       + alpha[:, 0].sum() + alpha[:, -1].sum())
    if border_alpha != 0:
        raise KilnRefusal(
            "The key left ground clinging to the border — border alpha must land "
            f"at exactly 0 and it landed at {border_alpha}. The firing is refused, "
            "not shipped translucent; repaint with a cleaner ground."
        )
    return np.dstack([rgb, alpha])


def despill_purple_gate(rgb):
    """The dark-thin-tube despill law, ported verbatim: pixels with
    r > g+18 AND b > g+18 AND min(r,b) > 85 are key survivors — neutralize
    to g×1.05. The gate spares terracotta (b < g), wicker (b low), red
    blooms (b low at that brightness), and blue coats (r fails); it catches
    exactly the lavender that magenta leaves on black bicycle frames."""
    out = rgb.copy()
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    gate = (r > g + 18) & (b > g + 18) & (np.minimum(r, b) > 85)
    cure = np.clip(np.rint(g.astype(np.float32) * 1.05), 0, 255).astype(rgb.dtype)
    out[..., 0][gate] = cure[gate]
    out[..., 2][gate] = cure[gate]
    return out


def crop_to_alpha_bbox(rgba, pad=ALPHA_BBOX_PAD):
    """The +6 px alpha-bbox crop law. The consumer projects the mesh bbox
    onto the FULL texture — an uncropped hide dresses the whole prop in
    key-colour padding (the first mounted bike was uniformly magenta)."""
    alpha = rgba[..., 3]
    ys, xs = np.nonzero(alpha)
    if not len(ys):
        raise KilnRefusal(
            "The keyed hide is entirely transparent — there is no subject to crop. "
            "The paint never held; fire again with a different seed."
        )
    top = max(0, int(ys.min()) - pad)
    bottom = min(rgba.shape[0], int(ys.max()) + 1 + pad)
    left = max(0, int(xs.min()) - pad)
    right = min(rgba.shape[1], int(xs.max()) + 1 + pad)
    return rgba[top:bottom, left:right]


STAND_THIN = ("bike", "bicycle", "fiets", "wheel", "fence", "railing", "ladder",
              "gate", "sign", "mirror", "door", "shutter", "panel", "screen",
              "lattice", "trellis")
LAY_LONG = ("trike", "bench", "hose", "canoe", "sled", "wagon", "cart", "log",
            "plank", "beam")


def orient_hint(subject_phrase):
    """`standThin` (thinnest-axis-to-z) for subjects whose thin axis is their
    identity — a bicycle is a plane with ambitions; `layLong` (longest-axis-
    to-x) for length-dominant bodies. Advisory copy for the Rack card — it
    terminates at the human writing the mount code, never travels through
    pack-props.mjs (which has no metadata channel)."""
    words = subject_phrase.lower()
    if any(w in words for w in STAND_THIN):
        return "standThin"
    return "layLong"


# ------------------------------------------------------------- the firing

def _keyed_hide(painting_path):
    """paint → key (border-alpha gate) → purple-gated despill → +6 px crop."""
    rgba = key_prop_image(painting_path)
    rgba[..., :3] = despill_purple_gate(rgba[..., :3])
    return crop_to_alpha_bbox(rgba)


def candidate_dir(candidate_id):
    """THE write boundary: every artifact a firing produces lives here and
    nowhere else. pack-queue/ is reachable only through rack_approve."""
    return KILN_OUT / candidate_id


def _new_candidate_id():
    return f"kiln-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"


def _write_recipe(cdir, recipe):
    (cdir / "recipe.json").write_text(json.dumps(recipe, indent=1))


def read_recipe(candidate_id):
    try:
        return json.loads((candidate_dir(candidate_id) / "recipe.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def detect_shredding(glb_path, expected_parts=1):
    """Delegates to the Turntable — one instrument, two consumers. This bool
    at the Kiln's gate and the full report at the Rack's card are the SAME
    computation (`turntable_qa`); building it twice would let them drift."""
    qa = turntable_qa(glb_path, expected_parts=expected_parts)
    return not qa.passed


def kiln_fire(subject, octree=DEFAULT_OCTREE, threshold=DEFAULT_THRESHOLD,
              two_sided=False, seed=None, expected_parts=1,
              clear_set=None, log=None):
    """The eight steps as one call. Returns a KilnResult; the candidate is
    parked on the Curing Rack (`kiln-output/<id>/`, status pending) — it
    NEVER auto-ships. The fail-closed guard runs at every model-swap
    boundary, not once at the door: paint → (guard) mesh → (guard) grounding.
    """
    clear_set = clear_set or stagehands.clear_the_set
    say = log or (lambda _m: None)
    seed = int(seed) if seed is not None else int(time.time()) % 2 ** 31
    cid = _new_candidate_id()
    cdir = candidate_dir(cid)
    cdir.mkdir(parents=True, exist_ok=True)

    say(f"the kiln lights — painting '{subject}' (seed {seed})")
    painting = paint_subject(subject, seed, prefix=f"Kiln-{cid}")
    hide = _keyed_hide(painting)
    hide_path = cdir / f"{cid}-hide.png"
    Image.fromarray(hide, "RGBA").save(hide_path)

    back_path = None
    if two_sided:
        say("asymmetric subject declared — painting the far side (identity-anchored)")
        sitter_name = f"kiln-front-{uuid4().hex[:8]}.png"
        COMFY_IN.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(painting, COMFY_IN / sitter_name)
        back_painting = paint_subject(subject, seed, prefix=f"Kiln-{cid}-back",
                                      back_of=sitter_name)
        back = _keyed_hide(back_painting)
        back_path = cdir / f"{cid}-back.png"
        Image.fromarray(back, "RGBA").save(back_path)

    # Swap boundary: evict the still-resident paint model before the mesh.
    ok, free = clear_set(MESH_VRAM_GB)
    if not ok:
        raise KilnColdError(
            f"The stagehands could not clear the GPU for the mesh stage — "
            f"{free:.1f} GB free, {MESH_VRAM_GB} needed. The Face Shop is refusing "
            "to strike its set; give it a moment and fire again."
        )
    say(f"firing the mesh at octree {octree}, threshold {threshold}")
    glb_src = fire_mesh(hide_path, octree, threshold, seed=seed, prefix=cid)
    glb_path = cdir / f"{cid}.glb"
    shutil.copyfile(glb_src, glb_path)

    refire_count = 0
    used_octree, used_threshold = octree, threshold
    shredded = detect_shredding(glb_path, expected_parts=expected_parts)
    if shredded:
        say(f"the silhouette tattered at octree {octree} — "
            f"refiring once at {REFIRE_OCTREE}/{REFIRE_THRESHOLD}")
        ok, free = clear_set(MESH_VRAM_GB)
        if not ok:
            raise KilnColdError(
                f"The stagehands could not clear the GPU for the refire — "
                f"{free:.1f} GB free, {MESH_VRAM_GB} needed."
            )
        glb_src = fire_mesh(hide_path, REFIRE_OCTREE, REFIRE_THRESHOLD,
                            seed=seed, prefix=f"{cid}-refire")
        shutil.copyfile(glb_src, glb_path)
        refire_count = 1
        used_octree, used_threshold = REFIRE_OCTREE, REFIRE_THRESHOLD
        shredded = detect_shredding(glb_path, expected_parts=expected_parts)
        if shredded:
            say("still tattering after the refire — parking it flagged for a human eye")

    recipe = {
        "id": cid,
        "subject": subject,
        "seed": seed,
        "octree": used_octree,
        "threshold": used_threshold,
        "first_octree": octree,
        "first_threshold": threshold,
        "refire_count": refire_count,
        "shredding_detected": shredded,
        "orient_hint": orient_hint(subject),
        "two_sided": two_sided,
        "expected_parts": expected_parts,
        "status": "pending",
        "fired_at": datetime.now().isoformat(timespec="seconds"),
        "files": {
            "glb": glb_path.name,
            "hide": hide_path.name,
            "back": back_path.name if back_path else None,
        },
    }
    _write_recipe(cdir, recipe)
    say(f"parked on the Curing Rack as {cid} — pending a thumb on Approve")
    return KilnResult(
        id=cid, subject=subject, glb_path=str(glb_path), hide_path=str(hide_path),
        back_path=str(back_path) if back_path else None,
        octree=used_octree, threshold=used_threshold, seed=seed,
        refire_count=refire_count, shredding_detected=shredded,
        orient_hint=recipe["orient_hint"], two_sided=two_sided,
    )


def appraise_candidate(candidate_id, clear_set=None):
    """Run the full Turntable report (deterministic checks + the qwen3-vl
    grounding that writes the Canister label) and file qa.json on the
    candidate. Invoked automatically after every firing; re-runnable from
    the Rack."""
    recipe = read_recipe(candidate_id)
    if recipe is None:
        raise RackRefusal(f"No candidate '{candidate_id}' is curing on the rack.")
    cdir = candidate_dir(candidate_id)
    qa = turntable_qa(
        cdir / recipe["files"]["glb"],
        expected_parts=recipe.get("expected_parts", 1),
        subject_phrase=recipe["subject"],
        clear_set=clear_set or stagehands.clear_the_set,
    )
    write_qa(cdir, qa)
    if qa.canister_label:
        recipe["canister_label"] = qa.canister_label
        _write_recipe(cdir, recipe)
    return qa


# ------------------------------------------------------------ the Curing Rack

def rack_list():
    """Every candidate still on the rack, newest first, with recipe + QA.
    There is deliberately no `rejected` state: the panel has exactly two
    buttons, and a candidate nobody approves simply stays pending — the
    Rack IS the reject pile."""
    if not KILN_OUT.exists():
        return []
    items = []
    for d in KILN_OUT.iterdir():
        if not d.is_dir():
            continue
        try:
            recipe = json.loads((d / "recipe.json").read_text())
        except (OSError, json.JSONDecodeError):
            continue  # an unreadable label never blocks the shelf
        try:
            qa = json.loads((d / "qa.json").read_text())
        except (OSError, json.JSONDecodeError):
            qa = None
        frames = sorted(p.name for p in (d / "turn").glob("*.png"))
        items.append({
            "id": d.name,
            "recipe": recipe,
            "qa": qa,
            "frames": [f"{d.name}/turn/{f}" for f in frames],
            "hide": f"{d.name}/{recipe['files']['hide']}" if recipe.get("files") else None,
        })
    items.sort(key=lambda it: it["recipe"].get("fired_at", ""), reverse=True)
    return items


def rack_approve(candidate_id, pack_name):
    """The Scientist's thumb. Moves GLB + hide (+ back) into pack-queue/
    under a name pack-props.mjs's regex accepts — the ONLY door from a
    firing to the pack queue. Collisions are refused voiced; nothing is
    ever overwritten."""
    recipe = read_recipe(candidate_id)
    if recipe is None:
        raise RackRefusal(f"No candidate '{candidate_id}' is curing on the rack.")
    if recipe.get("status") != "pending":
        raise RackRefusal(
            f"'{candidate_id}' is not pending — it is {recipe.get('status')}. "
            "Only a curing candidate can be approved."
        )
    pack_name = (pack_name or "").strip()
    if not PACK_NAME_RE.match(pack_name):
        raise RackRefusal(
            f"'{pack_name}' will not survive the packer — pack names are "
            "lowercase letters, digits, and dashes only (pack-props.mjs's own law)."
        )
    PACK_QUEUE.mkdir(parents=True, exist_ok=True)
    if (PACK_QUEUE / f"{pack_name}.glb").exists():
        raise RackRefusal(
            f"'{pack_name}' is already curing on that shelf — give this one a "
            "different name. Nothing gets overwritten."
        )
    cdir = candidate_dir(candidate_id)
    files = recipe["files"]
    shutil.copyfile(cdir / files["glb"], PACK_QUEUE / f"{pack_name}.glb")
    shutil.copyfile(cdir / files["hide"], PACK_QUEUE / f"{pack_name}-hide.png")
    if files.get("back"):
        shutil.copyfile(cdir / files["back"], PACK_QUEUE / f"{pack_name}-back.png")
    recipe["status"] = "approved"
    recipe["pack_name"] = pack_name
    recipe["approved_at"] = datetime.now().isoformat(timespec="seconds")
    _write_recipe(cdir, recipe)
    return {
        "approved": candidate_id,
        "pack_name": pack_name,
        "two_sided": bool(files.get("back")),
    }


def rack_refire(candidate_id, octree, threshold, clear_set=None, log=None):
    """Re-fire ONLY the mesh stage on the candidate's stored hide — the
    painting the Scientist judged is the painting that gets re-meshed
    (byte-identical; Klein would paint a different prop every run). The
    original stays on record as `refired`, superseded, never deleted —
    the Rack's own audit trail. Returns the new candidate id."""
    clear_set = clear_set or stagehands.clear_the_set
    say = log or (lambda _m: None)
    recipe = read_recipe(candidate_id)
    if recipe is None:
        raise RackRefusal(f"No candidate '{candidate_id}' is curing on the rack.")
    if recipe.get("status") != "pending":
        raise RackRefusal(
            f"'{candidate_id}' is not pending — it is {recipe.get('status')}. "
            "A full repaint is a new firing from the Kiln tab, not a Refire."
        )
    octree = int(octree)
    threshold = float(threshold)
    old_dir = candidate_dir(candidate_id)
    new_id = _new_candidate_id()
    new_dir = candidate_dir(new_id)
    new_dir.mkdir(parents=True, exist_ok=True)

    old_hide = old_dir / recipe["files"]["hide"]
    new_hide = new_dir / f"{new_id}-hide.png"
    shutil.copyfile(old_hide, new_hide)  # byte-identical — the judged painting
    new_back = None
    if recipe["files"].get("back"):
        new_back = new_dir / f"{new_id}-back.png"
        shutil.copyfile(old_dir / recipe["files"]["back"], new_back)

    ok, free = clear_set(MESH_VRAM_GB)
    if not ok:
        raise KilnColdError(
            f"The stagehands could not clear the GPU for the refire — "
            f"{free:.1f} GB free, {MESH_VRAM_GB} needed."
        )
    say(f"refiring {candidate_id} at octree {octree}, threshold {threshold}")
    glb_src = fire_mesh(new_hide, octree, threshold,
                        seed=recipe["seed"], prefix=new_id)
    new_glb = new_dir / f"{new_id}.glb"
    shutil.copyfile(glb_src, new_glb)
    shredded = detect_shredding(new_glb, expected_parts=recipe.get("expected_parts", 1))

    new_recipe = dict(recipe)
    new_recipe.update({
        "id": new_id,
        "octree": octree,
        "threshold": threshold,
        "refire_count": int(recipe.get("refire_count", 0)) + 1,
        "refired_from": candidate_id,
        "shredding_detected": shredded,
        "status": "pending",
        "fired_at": datetime.now().isoformat(timespec="seconds"),
        "files": {
            "glb": new_glb.name,
            "hide": new_hide.name,
            "back": new_back.name if new_back else None,
        },
    })
    new_recipe.pop("pack_name", None)
    new_recipe.pop("approved_at", None)
    _write_recipe(new_dir, new_recipe)

    recipe["status"] = "refired"
    recipe["superseded_by"] = new_id
    _write_recipe(old_dir, recipe)
    say(f"the refire parked as {new_id}; {candidate_id} stays on record, superseded")
    return new_id
