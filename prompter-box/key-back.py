#!/usr/bin/env python
"""Key one still plate off its green gradient ground — the back-view keyer.

Graduated from the Parlour square-back patron arc (2026-08-02): the flat-
median keyer refused these plates (a Krea RAW ground is a smooth gradient,
ring residuals ~80 corner-to-corner), which is why the Kiln's
key_prop_image now fits a quadratic background surface from the border
ring and keys against it locally. This CLI is that law plus the strong
green despill and the Kiln's +6 px alpha-bbox crop — enclosed islands key
only if chroma-green (olive orc skin never qualifies), and border alpha
must land at exactly 0 or the firing is refused (the fail-closed
contract).

Usage: key-back.py SRC.jpg OUT.png

Run with a machine venv's python (numpy + PIL + scipy — the Keymaster's
exception; see requirements.txt and the runbook).
"""
import sys

from PIL import Image

import kiln

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: key-back.py SRC.jpg OUT.png")
    src, out = sys.argv[1], sys.argv[2]
    try:
        rgba = kiln.key_prop_image(src)
    except kiln.KilnRefusal as refusal:
        sys.exit(f"REFUSED: {refusal}")
    despilled = kiln.despill_green_gate(rgba[..., :3], rgba[..., 3], edge_band=0)
    cured = int((despilled != rgba[..., :3]).any(axis=2).sum())
    rgba[..., :3] = despilled
    rgba = kiln.crop_to_alpha_bbox(rgba)
    Image.fromarray(rgba).save(out)
    print(f"keyed {out}: {rgba.shape[1]}x{rgba.shape[0]}, despilled {cured} px")
