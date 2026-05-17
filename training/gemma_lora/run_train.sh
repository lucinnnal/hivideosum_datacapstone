#!/usr/bin/env bash
# LoRA fine-tuning launcher
# Usage:
#   bash run_train.sh                        # config.yaml 사용
#   bash run_train.sh --config my.yaml       # 커스텀 config 지정
set -euo pipefail

CONFIG="config.yaml"
if [[ "${1:-}" == "--config" && -n "${2:-}" ]]; then
    CONFIG="$2"
fi

# ---------------------------------------------------------------------------
# CUDA / memory settings
# ---------------------------------------------------------------------------
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
export TORCH_ALLOW_TF32=1

# ---------------------------------------------------------------------------
# HuggingFace cache (optional — fast disk 경로로 변경 가능)
# ---------------------------------------------------------------------------
# export HF_HOME="/path/to/fast/disk/.cache/huggingface"

echo "=========================================="
echo " LoRA Fine-tuning"
echo " Config: $CONFIG"
echo "=========================================="

python train_lora.py --config "$CONFIG"