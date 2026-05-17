#!/usr/bin/env bash
# Start vLLM server for the configured model family.
# Model-specific args are loaded from configs/{MODEL_FAMILY}.yaml.
# Override any value via environment variable (see launch_vllm.py for the full list).

set -euo pipefail

MODEL_FAMILY="${MODEL_FAMILY:-exaone40}"
echo "[start_vllm_server] MODEL_FAMILY=${MODEL_FAMILY}"

exec python3 /app/scripts/launch_vllm.py
