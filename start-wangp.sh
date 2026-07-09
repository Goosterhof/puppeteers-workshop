#!/usr/bin/env bash
# The Puppeteer's Stage — Wan2GP (SCAIL-2 motion transfer, OmniVoice, Relay Prompt)
# UI: http://localhost:7860  (reachable from the Windows browser; WSL2 forwards localhost)
set -euo pipefail
cd "$(dirname "$0")/Wan2GP"
exec .venv/bin/python wgp.py "$@"
