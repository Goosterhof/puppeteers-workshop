#!/usr/bin/env bash
# The Puppeteer's Face Shop — ComfyUI (Flux 2 Klein 9B character swap)
# UI: http://localhost:8188  (reachable from the Windows browser; WSL2 forwards localhost)
set -euo pipefail
cd "$(dirname "$0")/ComfyUI"
exec .venv/bin/python main.py "$@"
