#!/usr/bin/env python
"""The stance cutter — cut N idle stances from a green-ground i2v take.

The Bull's recipe (the Parlour e8 furniture arc, 2026-08-02), graduated
from the session scratchpad: extract frames, compute motion energy, pick
the stillest frame in each of N beat windows (the base stance comes from
the take's own EARLY frames — the seam law), key each against the Kiln's
quadratic green-gradient model, despill (strong gate + 3 px edge band),
register by foot centroid with a zero-fill shift (never np.roll — a
wrapped column plants a foot on the far side of the frame), and
union-crop the set with a +6 px pad so every stance shares one canvas.

i2v output carries no Klein vignette, so frames key through
kiln.key_prop_pixels directly — the path half's 14 px crop never runs.

Usage: cut-stances.py TAKE.mp4 OUTDIR PREFIX [N]
Emits OUTDIR/PREFIX-i{0..N-1}.png  (N defaults to 5)

Run with a machine venv's python (numpy + PIL + scipy — the Keymaster's
exception; see requirements.txt and the runbook).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import kiln

FFMPEG = str(Path.home() / ".local/bin/ffmpeg")
PAD = 6  # the same +6 px law the Kiln's alpha-bbox crop carries


def key_frame(rgb):
    """Quadratic-gradient key + green despill, straight from the Kiln's laws."""
    rgba = kiln.key_prop_pixels(rgb)
    rgba[..., :3] = kiln.despill_green_gate(rgba[..., :3], rgba[..., 3])
    return rgba


def foot_centroid(rgba):
    """Weighted x-centroid of the lowest 6% of the subject — the feet."""
    a = rgba[..., 3] > 0
    ys = np.nonzero(a.any(axis=1))[0]
    band = a[max(ys.max() - int(0.06 * (ys.max() - ys.min())), 0):ys.max() + 1]
    cols = band.sum(axis=0).astype(np.float64)
    return (cols * np.arange(len(cols))).sum() / max(cols.sum(), 1)


def shift_zero_fill(rgba, dx):
    """Horizontal shift that fills with transparency instead of wrapping."""
    moved = np.zeros_like(rgba)
    if dx >= 0:
        moved[:, dx:] = rgba[:, :rgba.shape[1] - dx] if dx else rgba
    else:
        moved[:, :dx] = rgba[:, -dx:]
    return moved


def cut_stances(mp4, outdir, prefix, n_stances=5):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(mp4),
                        f"{td}/f%04d.png"], check=True)
        files = sorted(Path(td).glob("f*.png"))
        small = [np.asarray(Image.open(f).convert("L").reduce(4), np.float32)
                 for f in files]
        energy = [0.0] + [float(np.abs(small[i] - small[i - 1]).mean())
                          for i in range(1, len(small))]
        n = len(files)
        windows = [(int(n * k / n_stances), int(n * (k + 1) / n_stances))
                   for k in range(n_stances)]
        windows[0] = (1, max(int(n * 0.15), 3))  # base from the take's own early frames
        picks = [min(range(a, b), key=lambda i: energy[i]) for a, b in windows]
        print("picked frames:", picks, "of", n)
        keyed = [key_frame(np.asarray(Image.open(files[i]).convert("RGB")))
                 for i in picks]
    ref = foot_centroid(keyed[0])
    shifted = [keyed[0]] + [
        shift_zero_fill(k, int(round(ref - foot_centroid(k)))) for k in keyed[1:]]
    union = np.zeros(shifted[0].shape[:2], bool)
    for k in shifted:
        union |= k[..., 3] > 0
    ys, xs = np.nonzero(union)
    y0, y1 = max(ys.min() - PAD, 0), ys.max() + PAD + 1
    x0, x1 = max(xs.min() - PAD, 0), xs.max() + PAD + 1
    for i, k in enumerate(shifted):
        Image.fromarray(k[y0:y1, x0:x1]).save(outdir / f"{prefix}-i{i}.png")
    print("cut", prefix, f"{x1 - x0}x{y1 - y0}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit("Usage: cut-stances.py TAKE.mp4 OUTDIR PREFIX [N]")
    try:
        cut_stances(sys.argv[1], sys.argv[2], sys.argv[3],
                    int(sys.argv[4]) if len(sys.argv) > 4 else 5)
    except kiln.KilnRefusal as refusal:
        sys.exit(f"REFUSED: {refusal}")
