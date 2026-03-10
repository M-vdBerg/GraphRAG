# ─── Stage 1: dependency install ─────────────────────────────────────────────
FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime AS deps

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip setuptools

COPY pyproject.toml .
COPY src/ ./src/
# Install only the watcher extras (no MCP deps)
RUN pip install --no-cache-dir ".[watcher]"

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Non-root user for least-privilege operation
RUN groupadd -g 1001 appgroup \
    && useradd -u 1001 -g appgroup -m -s /bin/bash appuser

# Copy installed packages from deps stage (PyTorch image uses conda)
COPY --from=deps /opt/conda/lib/python3.10/site-packages /opt/conda/lib/python3.10/site-packages
COPY --from=deps /opt/conda/bin /opt/conda/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY src/ ./src/

RUN chown -R appuser:appgroup /app
USER appuser

# HuggingFace model cache (mount a host volume here to persist downloads)
ENV HF_HOME=/home/appuser/.cache/huggingface

CMD ["python", "-m", "graphrag.watcher.main"]
