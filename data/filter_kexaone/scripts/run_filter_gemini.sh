#!/usr/bin/env bash
# Run the Gemini (Vertex AI) comment filtering script.
# Authentication: GCP Application Default Credentials (ADC).
#   Run once before first use: gcloud auth application-default login
#
# Generation config is loaded from configs/gemini.yaml. Pass env vars to override.
#
# Environment variables:
#   GEMINI_CONFIG      : path to config YAML (default: configs/gemini.yaml)
#   INPUT_FILE         : input JSONL path  (default: data/combined_data_merged.jsonl)
#   OUTPUT_FILE        : output JSONL path (default: data/filtered_comments_gemini.jsonl)
#   GCP_PROJECT        : GCP project id (override YAML)
#   GCP_LOCATION       : GCP region (override YAML)
#   TEMPERATURE        : override temperature from YAML
#   TOP_P              : override top_p from YAML
#   MAX_OUTPUT_TOKENS  : override max_output_tokens from YAML
#   THINKING_LEVEL     : override thinking level (none | low | medium | high)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

GEMINI_CONFIG="${GEMINI_CONFIG:-configs/gemini.yaml}"
INPUT_FILE="${INPUT_FILE:-data/combined_data_merged.jsonl}"
OUTPUT_FILE="${OUTPUT_FILE:-data/filtered_comments_gemini.jsonl}"

echo "========================================"
echo "  Running Gemini comment filtering (Vertex AI)"
echo "  Config      : ${GEMINI_CONFIG}"
echo "  Input       : ${INPUT_FILE}"
echo "  Output      : ${OUTPUT_FILE}"
echo "========================================"

EXTRA_ARGS=()
[ -n "${GCP_PROJECT:-}"        ] && EXTRA_ARGS+=(--project           "${GCP_PROJECT:-}")
[ -n "${GCP_LOCATION:-}"       ] && EXTRA_ARGS+=(--location          "${GCP_LOCATION:-}")
[ -n "${TEMPERATURE:-}"        ] && EXTRA_ARGS+=(--temperature       "${TEMPERATURE:-}")
[ -n "${TOP_P:-}"              ] && EXTRA_ARGS+=(--top-p             "${TOP_P:-}")
[ -n "${MAX_OUTPUT_TOKENS:-}"  ] && EXTRA_ARGS+=(--max-output-tokens "${MAX_OUTPUT_TOKENS:-}")
[ -n "${THINKING_LEVEL:-}"     ] && EXTRA_ARGS+=(--thinking-level    "${THINKING_LEVEL:-}")

python filter_comments_with_gemini.py \
    --config  "${GEMINI_CONFIG}" \
    --input   "${INPUT_FILE}" \
    --output  "${OUTPUT_FILE}" \
    ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
