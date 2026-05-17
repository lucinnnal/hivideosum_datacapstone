#!/bin/bash

# =======================================================
# Run EXAONE 4.0 32B Comment Filtering (Serve + Inference)
# =======================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ $# -lt 1 ]; then
    INPUT_FILE="comment_results/combined_data.jsonl"
else
    INPUT_FILE="$1"
fi

if [ $# -lt 2 ]; then
    OUTPUT_FILE="comment_results/filtered_comments_exaone.jsonl"
else
    OUTPUT_FILE="$2"
fi

TP_SIZE="${3:-1}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}EXAONE Comment Filter Pipeline${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Initialize conda
eval "$(conda shell.bash hook)"
conda activate datacapstone

echo -e "${YELLOW}Using Python from: $(which python)${NC}"

# Check for required python packages
if ! python -c "import openai" &> /dev/null; then
    echo -e "${YELLOW}Installing openai package...${NC}"
    pip install openai
fi

# Start vLLM Server in the background
echo -e "${GREEN}Starting EXAONE vLLM server in the background (TP=${TP_SIZE})...${NC}"

# Run the vLLM server directly and capture its PID
vllm serve LGAI-EXAONE/EXAONE-4.0-32B \
  --tensor-parallel-size "$TP_SIZE" \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --reasoning-parser deepseek_r1 \
  --host 0.0.0.0 \
  --port 8000 > "$ROOT_DIR/exaone_serve.log" 2>&1 &
VLLM_PID=$!

echo -e "Server PID: $VLLM_PID"
echo -n "Waiting for server to become ready..."

# Wait until port 8000 is open and server is ready
MAX_RETRIES=60
RETRY_COUNT=0
SERVER_READY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8000/v1/models > /dev/null; then
        SERVER_READY=true
        break
    fi
    sleep 5
    RETRY_COUNT=$((RETRY_COUNT+1))
    echo -n "."
done

echo ""

if [ "$SERVER_READY" = false ]; then
    echo -e "${RED}Error: vLLM server failed to start or timed out.${NC}"
    echo "Check exaone_serve.log for details."
    kill $VLLM_PID 2>/dev/null || true
    exit 1
fi

echo -e "${GREEN}Server is ready! Starting filtering process...${NC}"

cd "$ROOT_DIR"
# Disable set -e temporarily to gracefully shutdown server if inference fails
set +e
python filter_comments_with_exaone.py --input "$INPUT_FILE" --output "$OUTPUT_FILE"
INFERENCE_EXIT_CODE=$?
set -e

echo -e "${YELLOW}Stopping vLLM server (PID: $VLLM_PID)...${NC}"
kill $VLLM_PID 2>/dev/null || true
wait $VLLM_PID 2>/dev/null || true

if [ $INFERENCE_EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Filtering complete!${NC}"
    echo -e "Output saved to: ${OUTPUT_FILE}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}Filtering failed with exit code $INFERENCE_EXIT_CODE.${NC}"
fi

exit $INFERENCE_EXIT_CODE
