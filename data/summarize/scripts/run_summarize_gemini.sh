#!/usr/bin/env bash
# Run the Gemini summarization script (Vertex AI + ADC).
# Generation config (temperature, top_p, max_output_tokens, thinking_level) is
# loaded from configs/gemini.yaml. Pass explicit env vars to override.
#
# Authentication: uses GCP Application Default Credentials (ADC).
#   Run once before first use: gcloud auth application-default login
#
# Environment variables:
#   GEMINI_CONFIG      : path to config YAML (default: configs/gemini.yaml)
#   INPUT_FILE         : input JSONL path  (default: data/filtered_combined_data.jsonl)
#   OUTPUT_FILE        : output JSONL path (default: data/summarized_data_gemini.jsonl)
#   TEMPERATURE        : override sampling temperature from YAML
#   TOP_P              : override top_p from YAML
#   MAX_OUTPUT_TOKENS  : override max_output_tokens from YAML
#   THINKING_LEVEL     : override thinking level (none | low | medium | high)

set -euo pipefail

GEMINI_CONFIG="${GEMINI_CONFIG:-configs/gemini.yaml}"
INPUT_FILE="${INPUT_FILE:-data/filtered_comments_kexaone_final_2.jsonl}"
OUTPUT_FILE="${OUTPUT_FILE:-data/summarized_data_gemini_3_flash_filtered.jsonl}"

echo "========================================"
echo "  Running Gemini summarization"
echo "  Config      : ${GEMINI_CONFIG}"
echo "  Input       : ${INPUT_FILE}"
echo "  Output      : ${OUTPUT_FILE}"
echo "========================================"

EXTRA_ARGS=()
[ -n "${TEMPERATURE:-}"      ] && EXTRA_ARGS+=(--temperature       "${TEMPERATURE:-}")
[ -n "${TOP_P:-}"            ] && EXTRA_ARGS+=(--top-p             "${TOP_P:-}")
[ -n "${MAX_OUTPUT_TOKENS:-}" ] && EXTRA_ARGS+=(--max-output-tokens "${MAX_OUTPUT_TOKENS:-}")
[ -n "${THINKING_LEVEL:-}"   ] && EXTRA_ARGS+=(--thinking-level    "${THINKING_LEVEL:-}")

python summarize_with_gemini.py \
    --config  "${GEMINI_CONFIG}" \
    --input   "${INPUT_FILE}" \
    --output  "${OUTPUT_FILE}" \
    ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
