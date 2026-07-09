#!/usr/bin/env python3
"""The Framewright — exact-resolution video cropper for the AI pipeline.

Motion transfer (SCAIL-2) degrades when the driving video's resolution does not
exactly match the generation resolution. The Framewright takes any source video
and produces output at an exact model resolution: largest possible crop window
of the target aspect ratio, positioned where you say, then scaled to the exact
target and (optionally) retimed to a fixed fps.

Usage:
  croptool.py input.mp4 --preset wan-720p-portrait
  croptool.py input.mp4 --size 1280x720 --gravity left --fps 30
  croptool.py input.mp4 --preset ltx2-1080p --shift-x 20 --preview 3.5

  --preview N renders a single frame at N seconds with the crop window drawn on
  it (no full render) so you can check framing before committing.

Requires ffmpeg/ffprobe on PATH (static builds in ~/.local/bin count).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PRESETS = {
    # Wan 2.1 / SCAIL-2 native resolutions
    "wan-480p-landscape": (832, 480),
    "wan-480p-portrait": (480, 832),
    "wan-720p-landscape": (1280, 720),
    "wan-720p-portrait": (720, 1280),
    "wan-square": (960, 960),
    # LTX2 (Relay Prompt / OmniNFT LoRA runs)
    "ltx2-1080p-landscape": (1920, 1080),
    "ltx2-1080p-portrait": (1080, 1920),
    # Flux 2 Klein keyframe stills
    "klein-1024": (1024, 1024),
}

GRAVITIES = ("center", "left", "right", "top", "bottom")


def die(msg: str) -> "sys.NoReturn":
    print(f"[framewright] {msg}", file=sys.stderr)
    raise SystemExit(1)


def probe(path: Path) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate,duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout
    except FileNotFoundError:
        die("ffprobe is not on PATH — install the static build into ~/.local/bin first.")
    except subprocess.CalledProcessError as e:
        die(f"ffprobe could not read {path}: {e.stderr.strip()}")
    streams = json.loads(out).get("streams") or []
    if not streams:
        die(f"{path} has no video stream — the Framewright frames video, not silence.")
    return streams[0]


def crop_window(src_w: int, src_h: int, dst_w: int, dst_h: int,
                gravity: str, shift_x: int, shift_y: int) -> tuple[int, int, int, int]:
    """Largest crop of the target aspect that fits the source, then positioned."""
    target_ar = dst_w / dst_h
    if src_w / src_h > target_ar:
        ch = src_h
        cw = int(src_h * target_ar) // 2 * 2
    else:
        cw = src_w
        ch = int(src_w / target_ar) // 2 * 2

    max_x, max_y = src_w - cw, src_h - ch
    x = {"left": 0, "right": max_x}.get(gravity, max_x // 2)
    y = {"top": 0, "bottom": max_y}.get(gravity, max_y // 2)
    x = min(max(x + max_x * shift_x // 100, 0), max_x)
    y = min(max(y + max_y * shift_y // 100, 0), max_y)
    return cw, ch, x, y


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    tgt = p.add_mutually_exclusive_group(required=True)
    tgt.add_argument("--preset", choices=sorted(PRESETS))
    tgt.add_argument("--size", metavar="WxH", help="exact target, e.g. 1280x720")
    p.add_argument("--gravity", choices=GRAVITIES, default="center")
    p.add_argument("--shift-x", type=int, default=0,
                   help="nudge window horizontally, -100..100 (%% of slack)")
    p.add_argument("--shift-y", type=int, default=0,
                   help="nudge window vertically, -100..100 (%% of slack)")
    p.add_argument("--fps", type=float, default=None,
                   help="force output fps (SCAIL-2 pairing: match your generation fps)")
    p.add_argument("--preview", type=float, metavar="SECONDS", default=None,
                   help="write a single PNG at this timestamp with the crop window drawn")
    p.add_argument("--crf", type=int, default=16, help="x264 quality (lower=better)")
    args = p.parse_args()

    if not args.input.exists():
        die(f"{args.input} does not exist — nothing to frame.")

    if args.preset:
        dst_w, dst_h = PRESETS[args.preset]
        tag = args.preset
    else:
        try:
            dst_w, dst_h = (int(v) for v in args.size.lower().split("x"))
        except ValueError:
            die(f"--size must look like 1280x720, got {args.size!r}")
        tag = f"{dst_w}x{dst_h}"

    info = probe(args.input)
    src_w, src_h = int(info["width"]), int(info["height"])
    cw, ch, x, y = crop_window(src_w, src_h, dst_w, dst_h,
                               args.gravity, args.shift_x, args.shift_y)

    print(f"[framewright] source {src_w}x{src_h} → window {cw}x{ch} at ({x},{y}) "
          f"→ exact {dst_w}x{dst_h}" + (f" @ {args.fps}fps" if args.fps else ""))

    if args.preview is not None:
        out = args.output or args.input.with_name(
            f"{args.input.stem}.preview-{tag}.png")
        vf = (f"drawbox=x={x}:y={y}:w={cw}:h={ch}:color=lime@0.8:thickness=6")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(args.preview),
               "-i", str(args.input), "-vf", vf, "-frames:v", "1", "-update", "1",
               str(out)]
    else:
        out = args.output or args.input.with_name(
            f"{args.input.stem}.{tag}{args.input.suffix}")
        vf = f"crop={cw}:{ch}:{x}:{y},scale={dst_w}:{dst_h}:flags=lanczos,setsar=1"
        if args.fps:
            vf += f",fps={args.fps}"
        cmd = ["ffmpeg", "-y", "-i", str(args.input), "-vf", vf,
               "-c:v", "libx264", "-crf", str(args.crf), "-preset", "slow",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", str(out)]

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        die("ffmpeg is not on PATH — install the static build into ~/.local/bin first.")
    except subprocess.CalledProcessError as e:
        die(f"ffmpeg exited {e.returncode} — the frame did not survive the cut.")
    print(f"[framewright] wrote {out}")


if __name__ == "__main__":
    main()
