#!/usr/bin/env python
"""Key one still plate off its gradient ground — the still-plate keyer.

Graduated from the Parlour square-back patron arc (2026-08-02): the flat-
median keyer refused these plates (a Krea RAW ground is a smooth gradient,
ring residuals ~80 corner-to-corner), which is why the Kiln's
key_prop_image now fits a quadratic background surface from the border
ring and keys against it locally. This CLI is that law plus the family's
strong despill and the Kiln's +6 px alpha-bbox crop — enclosed islands
key only if they wear the key colour's own chroma (olive orc skin never
qualifies), and border alpha must land at exactly 0 or the firing is
refused (the fail-closed contract).

The FAMILY picks the ground: green (default) or magenta — the character
key law (a green-skinned or green-glowing subject dissolves on green and
fires on magenta; the mean-orc profiles, 2026-08-13, were the magenta
family's first stills).

Usage: key-back.py SRC.jpg OUT.png [green|magenta]

Run with a machine venv's python (numpy + PIL + scipy — the Keymaster's
exception; see requirements.txt and the runbook).
"""
import sys

from PIL import Image

import kiln

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: key-back.py SRC.jpg OUT.png [green|magenta]")
    src, out = sys.argv[1], sys.argv[2]
    family = sys.argv[3] if len(sys.argv) > 3 else "green"
    try:
        rgba = kiln.key_prop_image(src, family=family)
    except kiln.KilnRefusal as refusal:
        sys.exit(f"REFUSED: {refusal}")
    if family == "magenta":
        despilled = kiln.despill_magenta_gate(rgba[..., :3], rgba[..., 3], edge_band=0)
    else:
        despilled = kiln.despill_green_gate(rgba[..., :3], rgba[..., 3], edge_band=0)
    cured = int((despilled != rgba[..., :3]).any(axis=2).sum())
    rgba[..., :3] = despilled
    rgba = kiln.crop_to_alpha_bbox(rgba)
    Image.fromarray(rgba).save(out)
    print(f"The hide is cut: {out} at {rgba.shape[1]}x{rgba.shape[0]}, "
          f"{cured} px of {family} spill cured, border alpha exactly 0.")
