#!/bin/bash

# Navigate to the project root directory
cd "$(dirname "$0")/.."

echo "================================================="
echo " YouTube Comment Filter with Gemini 2.5 Flash"
echo "================================================="

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Ensure GEMINI_API_KEY is set."
fi

# Run the python script
python filter_comments_with_gemini.py "$@"

echo "================================================="
echo " Filtering process completed!"
echo " Results are saved in comment_results/filtered_comments.jsonl"
echo "================================================="
