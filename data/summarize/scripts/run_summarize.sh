#!/usr/bin/env bash
# Run the summarization script against a running vLLM server.
# Generation config (temperature, top_p, max_tokens, chat_template_kwargs) is
# loaded from configs/{MODEL_FAMILY}.yaml. Pass explicit env vars to override.
#
# Environment variables:
#   MODEL_FAMILY : model config to use (default: exaone40)
#   VLLM_HOST    : vLLM server base URL (default: http://localhost:8000/v1)
#   INPUT_FILE   : input JSONL path  (default: data/filtered_combined_data.jsonl)
#   OUTPUT_FILE  : output JSONL path (default: data/summarized_data.jsonl)
#   TEMPERATURE  : override sampling temperature from YAML
#   TOP_P        : override top_p from YAML
#   MAX_TOKENS   : override max tokens from YAML

set -euo pipefail

MODEL_FAMILY="${MODEL_FAMILY:-exaone40}"
VLLM_HOST="${VLLM_HOST:-http://localhost:8000/v1}"
INPUT_FILE="${INPUT_FILE:-data/filtered_combined_data.jsonl}"
OUTPUT_FILE="${OUTPUT_FILE:-data/summarized_data.jsonl}"

echo "========================================"
echo "  Running summarization"
echo "  Model family: ${MODEL_FAMILY}"
echo "  Host        : ${VLLM_HOST}"
echo "  Input       : ${INPUT_FILE}"
echo "  Output      : ${OUTPUT_FILE}"
echo "========================================"

EXTRA_ARGS=()
[ -n "${TEMPERATURE:-}" ] && EXTRA_ARGS+=(--temperature "${TEMPERATURE}")
[ -n "${TOP_P:-}"        ] && EXTRA_ARGS+=(--top-p      "${TOP_P}")
[ -n "${MAX_TOKENS:-}"   ] && EXTRA_ARGS+=(--max-tokens "${MAX_TOKENS}")

python3 summarize_with_exaone.py \
    --model-family "${MODEL_FAMILY}" \
    --input        "${INPUT_FILE}" \
    --output       "${OUTPUT_FILE}" \
    --host         "${VLLM_HOST}" \
    "${EXTRA_ARGS[@]}"
