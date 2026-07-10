#!/usr/bin/env python3
"""The Keymaster — background removal for illustrated takes on flat grounds.

Plain ffmpeg colorkey chews interior creams (a tilted scroll catches the light
and lands inside the key's tolerance band — the TC-0057 toll take lost its wax
seals to it). This keyer is topology-aware instead of purely chromatic:

1. Estimate the background PER FRAME (median of the border ring — the flat
   ground wobbles a few RGB points frame to frame).
2. Candidate pixels sit within --tolerance of that estimate.
3. A candidate region is only keyed if it TOUCHES the frame border (the true
   ground always does; a scroll face never does) or is larger than --min-island
   (an enclosed pocket of real ground, e.g. inside an arm akimbo).
4. The kept mask is feathered (1px gaussian) and the frame is composited onto
   pure white — the web asset's `mix-blend-mode: multiply` contract.

Usage:
  keymaster.py IN.mp4 OUT.webm [--crop WxH+X+Y] [--tolerance 20]
               [--min-island 3000] [--crf 40]
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

FFMPEG = str(Path.home() / '.local/bin/ffmpeg')
BORDER_RING = 10


def key_frame(rgb: np.ndarray, tolerance: float, min_island: int) -> np.ndarray:
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
            labels[0], labels[-1], labels[:, 0], labels[:, -1],
        ]))
        sizes = ndimage.sum_labels(np.ones_like(labels), labels, index=np.arange(1, count + 1))
        keep = np.zeros(count + 1, dtype=bool)
        keep[border_labels] = True
        keep[1:][sizes >= min_island] = True
        keep[0] = False
        mask = keep[labels]
    else:
        mask = candidate

    soft = ndimage.gaussian_filter(mask.astype(np.float32), sigma=1.0)[..., None]
    out = rgb.astype(np.float32) * (1 - soft) + 255.0 * soft
    return out.clip(0, 255).astype(np.uint8)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--crop', help='WxH+X+Y ffmpeg crop window, e.g. 704x880+0+200')
    ap.add_argument('--tolerance', type=float, default=20.0)
    ap.add_argument('--min-island', type=int, default=3000)
    ap.add_argument('--crf', type=int, default=40)
    ap.add_argument('--fps', type=int, default=24)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / 'raw'
        keyed = Path(td) / 'keyed'
        raw.mkdir()
        keyed.mkdir()

        vf = []
        if args.crop:
            wh, _, xy = args.crop.partition('+')
            width, height = wh.split('x')
            x, y = xy.split('+')
            vf.append(f'crop={width}:{height}:{x}:{y}')
        cmd = [FFMPEG, '-y', '-v', 'error', '-i', args.src]
        if vf:
            cmd += ['-vf', ','.join(vf)]
        cmd += ['-vsync', '0', str(raw / '%04d.png')]
        subprocess.run(cmd, check=True)

        frames = sorted(raw.glob('*.png'))
        if not frames:
            print('no frames decoded', file=sys.stderr)
            return 1
        for frame in frames:
            rgb = np.asarray(Image.open(frame).convert('RGB'))
            Image.fromarray(key_frame(rgb, args.tolerance, args.min_island)).save(keyed / frame.name)

        subprocess.run([
            FFMPEG, '-y', '-v', 'error', '-framerate', str(args.fps),
            '-i', str(keyed / '%04d.png'),
            '-c:v', 'libvpx-vp9', '-crf', str(args.crf), '-b:v', '0',
            '-pix_fmt', 'yuv420p', '-an', args.dst,
        ], check=True)

    print(f'keyed {len(frames)} frames -> {args.dst}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
