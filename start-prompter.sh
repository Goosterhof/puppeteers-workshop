#!/usr/bin/env bash
# The Prompter's Box — the booth that feeds lines to the performers
# UI: http://localhost:7900  (reachable from the Windows browser; WSL2 forwards localhost)
# Needs: Ollama on :11434 for the Forge; ComfyUI on :8188 for Face Shop cues.
# Stage cues spawn wgp.py --process headlessly — keep the full Wan2GP UI closed.
set -euo pipefail
cd "$(dirname "$0")/prompter-box"
exec python3 server.py "$@"
