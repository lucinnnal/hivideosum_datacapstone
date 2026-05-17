# ── Base: PyTorch 2.6 + CUDA 12.6 + cuDNN 9 ──────────────────────────────────
FROM pytorch/pytorch:2.6.0-cuda12.6-cudnn9-runtime

# MODEL_FAMILY controls which model config is used at runtime.
# Build with: --build-arg MODEL_FAMILY=exaone40 (default) or exaone45
ARG MODEL_FAMILY=exaone40

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        git \
        wget \
    && rm -rf /var/lib/apt/lists/*

# ── Common Python dependencies (openai, pyyaml) ───────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── vLLM: standard release for exaone40, forked build for exaone45 ───────────
RUN if [ "${MODEL_FAMILY}" = "exaone45" ]; then \
        pip install --no-cache-dir \
            git+https://github.com/lkm2835/vllm.git@add-exaone4_5 \
            git+https://github.com/nuxlear/transformers.git@add-exaone4_5; \
    else \
        pip install --no-cache-dir vllm==0.10.0; \
    fi

# ── Application files ─────────────────────────────────────────────────────────
COPY summarize_with_exaone.py .
COPY configs/ configs/
COPY scripts/ scripts/
RUN chmod +x scripts/entrypoint.sh scripts/start_vllm_server.sh scripts/run_summarize.sh

# ── Data volume (mount input/output JSONL files here at runtime) ──────────────
VOLUME ["/app/data"]

# ── Default environment variables (override with -e in docker run) ────────────
ENV MODEL_FAMILY="${MODEL_FAMILY}" \
    TENSOR_PARALLEL_SIZE="1" \
    GPU_MEMORY_UTILIZATION="0.90" \
    VLLM_PORT="8000" \
    INPUT_FILE="data/filtered_combined_data.jsonl" \
    OUTPUT_FILE="data/summarized_data.jsonl" \
    MAX_WAIT_SEC="300"

EXPOSE 8000

ENTRYPOINT ["bash", "/app/scripts/entrypoint.sh"]
