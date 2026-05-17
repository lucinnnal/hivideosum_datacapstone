#!/usr/bin/env bash
# Container entrypoint:
#   1. Start vLLM server in the background.
#   2. Wait until the server is ready (health check).
#   3. Run the summarization script.
#   4. Shut down the vLLM server.

set -euo pipefail

VLLM_PORT="${VLLM_PORT:-8000}"
HEALTH_URL="http://localhost:${VLLM_PORT}/health"
MAX_WAIT_SEC="${MAX_WAIT_SEC:-300}"   # wait up to 5 min for model to load

# ── 1. Launch vLLM server ────────────────────────────────────────────────────
echo "[entrypoint] Starting vLLM server..."
bash /app/scripts/start_vllm_server.sh &
VLLM_PID=$!

# ── 2. Health check loop ─────────────────────────────────────────────────────
echo "[entrypoint] Waiting for vLLM server to be ready (max ${MAX_WAIT_SEC}s)..."
elapsed=0
until curl -sf "${HEALTH_URL}" > /dev/null 2>&1; do
    if [ "${elapsed}" -ge "${MAX_WAIT_SEC}" ]; then
        echo "[entrypoint] ERROR: vLLM server did not become ready within ${MAX_WAIT_SEC}s."
        kill "${VLLM_PID}" 2>/dev/null || true
        exit 1
    fi
    sleep 5
    elapsed=$((elapsed + 5))
    echo "[entrypoint]   ...still waiting (${elapsed}s elapsed)"
done
echo "[entrypoint] vLLM server is ready."

# ── 3. Run summarization ──────────────────────────────────────────────────────
export VLLM_HOST="http://localhost:${VLLM_PORT}/v1"
bash /app/scripts/run_summarize.sh
EXIT_CODE=$?

# ── 4. Shutdown ───────────────────────────────────────────────────────────────
echo "[entrypoint] Summarization finished (exit ${EXIT_CODE}). Stopping vLLM server..."
kill "${VLLM_PID}" 2>/dev/null || true
wait "${VLLM_PID}" 2>/dev/null || true

exit "${EXIT_CODE}"
