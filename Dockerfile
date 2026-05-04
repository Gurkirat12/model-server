FROM python:3.11-slim AS model-fetch

RUN pip install --no-cache-dir huggingface-hub

RUN hf download \
    TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF \
    tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
    --local-dir /models


FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

RUN CMAKE_ARGS="-DLLAMA_BLAS=OFF -DLLAMA_CUBLAS=OFF" \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/app

COPY --from=builder /install /usr/local

COPY --from=model-fetch /models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
    /opt/app/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

COPY app/main.py     /opt/app/app/main.py
COPY app/config.py   /opt/app/app/config.py

COPY model_manifest.yaml /opt/app/etc/default/model_manifest.yaml

COPY app/list_profiles.py /opt/app/bin/list-profiles
RUN chmod +x /opt/app/bin/list-profiles

COPY entrypoint.sh /opt/app/entrypoint.sh
RUN chmod +x /opt/app/entrypoint.sh

ENV PATH="/opt/app/bin:$PATH"

RUN useradd -m -u 1000 -s /bin/bash appuser \
    && chown -R appuser:appuser /opt/app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=6 \
    CMD curl -sf http://localhost:8000/v1/health/ready || exit 1

ENV PROFILE=balanced

ENTRYPOINT ["/opt/app/entrypoint.sh"]
