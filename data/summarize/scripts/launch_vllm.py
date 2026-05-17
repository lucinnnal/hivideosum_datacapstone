#!/usr/bin/env python3
"""
Launch vLLM OpenAI-compatible server with model-family-specific configuration.
Reads configs/{MODEL_FAMILY}.yaml and exec's vllm, so env var overrides still work.
"""

import os
import sys

import yaml


def load_config(model_family: str) -> dict:
    """Load YAML config for the given model family."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "configs", f"{model_family}.yaml")
    config_path = os.path.abspath(config_path)
    if not os.path.exists(config_path):
        print(f"[launch_vllm] ERROR: config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    """Build vLLM command from config + env vars and exec."""
    model_family = os.environ.get("MODEL_FAMILY", "exaone40")
    cfg = load_config(model_family)
    vllm_cfg = cfg.get("vllm", {})

    # Base args — env vars take precedence over YAML defaults
    model_name = os.environ.get("MODEL_NAME") or cfg["model_name"]
    tp_size = os.environ.get("TENSOR_PARALLEL_SIZE", "1")
    gpu_mem = os.environ.get("GPU_MEMORY_UTILIZATION", "0.90")
    port = os.environ.get("VLLM_PORT", "8000")
    max_model_len = os.environ.get("MAX_MODEL_LEN") or str(vllm_cfg.get("max_model_len", 8192))

    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", model_name,
        "--tensor-parallel-size", tp_size,
        "--gpu-memory-utilization", gpu_mem,
        "--max-model-len", max_model_len,
        "--port", port,
        "--host", "0.0.0.0",
    ]

    # Model-specific vLLM args from YAML
    if "reasoning_parser" in vllm_cfg:
        cmd += ["--reasoning-parser", vllm_cfg["reasoning_parser"]]

    served_model_name = cfg.get("served_model_name")
    if served_model_name:
        cmd += ["--served-model-name", served_model_name]

    print("========================================")
    print(f"  Model family : {model_family}")
    print(f"  Model        : {model_name}")
    print(f"  TP size      : {tp_size}")
    print(f"  Max model len: {max_model_len}")
    print(f"  Port         : {port}")
    if served_model_name:
        print(f"  Served as    : {served_model_name}")
    print("========================================")

    os.execvp(sys.executable, cmd)


if __name__ == "__main__":
    main()
