#!/usr/bin/env bash
# Run the K-EXAONE comment filtering script.
# Generation config is loaded from configs/kexaone.yaml. Pass env vars to override.
#
# Environment variables:
#   K_EXAONE_API_KEY   : K-EXAONE Bearer token (required; or set in .env)
#   KEXAONE_CONFIG     : path to config YAML (default: configs/kexaone.yaml)
#   INPUT_FILE         : input JSONL path  (default: data/combined_data_merged.jsonl)
#   OUTPUT_FILE        : output JSONL path (default: data/filtered_comments_kexaone.jsonl)
#   TEMPERATURE        : override temperature from YAML
#   TOP_P              : override top_p from YAML
#   MAX_TOKENS         : override max_tokens from YAML

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

if [ -z "${K_EXAONE_API_KEY:-}" ]; then
    echo "Error: K_EXAONE_API_KEY is not set."
    echo "  export K_EXAONE_API_KEY=your_bearer_token  (or add it to .env)"
    exit 1
fi

KEXAONE_CONFIG="${KEXAONE_CONFIG:-configs/kexaone.yaml}"
INPUT_FILE="${INPUT_FILE:-data/combined_data_no_overlap_merged.jsonl}"
OUTPUT_FILE="${OUTPUT_FILE:-data/filtered_comments_kexaone_kkp.jsonl}"

echo "========================================"
echo "  Running K-EXAONE comment filtering"
echo "  Config      : ${KEXAONE_CONFIG}"
echo "  Input       : ${INPUT_FILE}"
echo "  Output      : ${OUTPUT_FILE}"
echo "========================================"

EXTRA_ARGS=()
[ -n "${TEMPERATURE:-}" ] && EXTRA_ARGS+=(--temperature "${TEMPERATURE:-}")
[ -n "${TOP_P:-}"       ] && EXTRA_ARGS+=(--top-p       "${TOP_P:-}")
[ -n "${MAX_TOKENS:-}"  ] && EXTRA_ARGS+=(--max-tokens  "${MAX_TOKENS:-}")

python filter_comments_with_kexaone.py \
    --config  "${KEXAONE_CONFIG}" \
    --input   "${INPUT_FILE}" \
    --output  "${OUTPUT_FILE}" \
    ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
