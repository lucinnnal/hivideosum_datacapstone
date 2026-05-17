#!/usr/bin/env bash
# Run the K-EXAONE summarization script (Elice mlapi.run).
# Generation config (temperature, top_p, max_tokens, presence_penalty,
# chat_template_kwargs) is loaded from configs/kexaone.yaml.
# Pass explicit env vars to override.
#
# Environment variables:
#   K_EXAONE_API_KEY   : K-EXAONE Bearer token (required; or set in .env)
#   KEXAONE_CONFIG     : path to config YAML (default: configs/kexaone.yaml)
#   INPUT_FILE         : input JSONL path  (default: data/filtered_combined_data.jsonl)
#   OUTPUT_FILE        : output JSONL path (default: data/summarized_data_kexaone.jsonl)
#   TEMPERATURE        : override sampling temperature from YAML
#   TOP_P              : override top_p from YAML
#   MAX_TOKENS         : override max_tokens from YAML
#   PRESENCE_PENALTY   : override presence_penalty from YAML

set -euo pipefail

# Load .env if present (project root)
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
    echo "  export K_EXAONE_API_KEY=your_api_key  (or add it to .env)"
    exit 1
fi

KEXAONE_CONFIG="${KEXAONE_CONFIG:-configs/kexaone.yaml}"
INPUT_FILE="${INPUT_FILE:-data/filtered_combined_data.jsonl}"
OUTPUT_FILE="${OUTPUT_FILE:-data/summarized_data_kexaone.jsonl}"

echo "========================================"
echo "  Running K-EXAONE summarization"
echo "  Config      : ${KEXAONE_CONFIG}"
echo "  Input       : ${INPUT_FILE}"
echo "  Output      : ${OUTPUT_FILE}"
echo "========================================"

EXTRA_ARGS=()
[ -n "${TEMPERATURE:-}"       ] && EXTRA_ARGS+=(--temperature      "${TEMPERATURE:-}")
[ -n "${TOP_P:-}"             ] && EXTRA_ARGS+=(--top-p            "${TOP_P:-}")
[ -n "${MAX_TOKENS:-}"        ] && EXTRA_ARGS+=(--max-tokens       "${MAX_TOKENS:-}")
[ -n "${PRESENCE_PENALTY:-}"  ] && EXTRA_ARGS+=(--presence-penalty "${PRESENCE_PENALTY:-}")

python summarize_with_kexaone.py \
    --config  "${KEXAONE_CONFIG}" \
    --input   "${INPUT_FILE}" \
    --output  "${OUTPUT_FILE}" \
    ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
