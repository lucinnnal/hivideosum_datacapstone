#!/bin/bash

# YouTube Channel Data Collector - Main Pipeline Script
# Usage: ./run.sh <channels.jsonl> [output_directory] [videos_per_channel]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}YouTube Channel Data Collector${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check arguments
if [ $# -lt 1 ]; then
    echo -e "${RED}Error: Missing required argument${NC}"
    echo "Usage: $0 <channels.jsonl> [output_directory] [videos_per_channel]"
    echo ""
    echo "  channels.jsonl       JSONL file with channel URLs"
    echo "  output_directory     Output directory (default: comment_results)"
    echo "  fetch_limit          Max videos to fetch per channel (default: 200)"
    exit 1
fi

CHANNELS_FILE="$1"
OUTPUT_DIR="${2:-comment_results}"
FETCH_LIMIT="${3:-300}"

# Initialize conda
eval "$(conda shell.bash hook)"

# Activate datacapstone environment
conda activate datacapstone

echo -e "${YELLOW}Using Python from: $(which python)${NC}"
echo ""

# Run channel collector
cd "$SCRIPT_DIR/.."
python channel_collector.py "$CHANNELS_FILE" \
    --output-dir "$OUTPUT_DIR" \
    --fetch-limit "$FETCH_LIMIT" \
    --max-comments 100

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}Data collection complete!${NC}"
    echo -e "Output directory: ${YELLOW}${OUTPUT_DIR}/${NC}"
    echo ""
    echo "Next step: Run Gemini summary generation:"
    echo -e "  ${YELLOW}./run_gemini.sh ${OUTPUT_DIR}/combined_data.jsonl${NC}"
fi

exit $EXIT_CODE
