#!/usr/bin/env bash
# VERITAS - start the lab on macOS / Linux.  Usage:  ./scripts/start_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
PORT="${VERITAS_PORT:-8000}"
if [ ! -d .venv ]; then echo "Setting up Python environment (needs internet once)..."; uv sync; fi
if [ ! -f models/ai_generated/model.safetensors ]; then
  echo "Models missing - downloading (needs internet once)..."; uv run python scripts/download_models.py
fi
echo ""
echo "  VERITAS - Deepfake Forensics Lab"
echo "  Starting the forensic engine on http://localhost:${PORT}/  (Ctrl+C to stop)"
echo ""
( for i in $(seq 1 180); do
    if curl -sf "http://localhost:${PORT}/api/health" >/dev/null 2>&1; then
      (command -v open >/dev/null && open "http://localhost:${PORT}/") || (command -v xdg-open >/dev/null && xdg-open "http://localhost:${PORT}/") || true
      break
    fi; sleep 1
  done ) &
# Use the project's own Python directly: works with no internet (uv run may try to re-sync the environment).
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port "${PORT}" --log-level warning
fi
exec uv run uvicorn server.app:app --host 127.0.0.1 --port "${PORT}" --log-level warning
