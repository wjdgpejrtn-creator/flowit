# llm-base container — llama.cpp server + Python BGE-M3 on one CUDA image.
#
# Build is normally driven by `modal deploy services/agents/llm-base/main.py`
# (Modal builds the image remotely). For local sanity:
#   docker build -f services/agents/llm-base/Dockerfile -t llm-base .
#
# Base must match the upstream llama.cpp image (Ubuntu 24.04 + CUDA 12.8) so
# glibc/libstdc++ ABIs line up with the binary copied below — copying a
# 24.04-built llama-server onto a 22.04 runtime breaks at GLIBCXX symbol
# resolution.
FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        python3 python3-venv \
        libcurl4 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 10001 appuser \
    && python3 -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Pre-built llama-server (CUDA 12, Ubuntu 24.04) from the official image.
# Bump the tag deliberately when picking up llama.cpp fixes — b8967 (April
# 2026) is past the Gemma 4 day-0 PRs (#21326 parser + #21343 tokenizer);
# earlier builds fail on `unknown model architecture: 'gemma4'`.
#
# Two distinct loaders need to find the .so files:
#   - transitive linking (libllama-common.so.0 etc) — ld.so reads
#     /etc/ld.so.cache, populated by ldconfig.
#   - ggml plugin loader (libggml-cuda.so) — `ggml_backend_load_all()`
#     scans the binary's directory and cwd for libggml-*.so. GGML_BACKEND_PATH
#     env is *not* a directory hint — ggml passes it straight to dlopen, so
#     it must point at a single .so file. Setting it to a directory boots to
#     CPU silently.
# Co-locating binary + .so in /usr/local/bin and registering that path with
# ldconfig satisfies both loaders without env-var trickery.
COPY --from=ghcr.io/ggml-org/llama.cpp:server-cuda12-b8967 /app/llama-server /usr/local/bin/llama-server
COPY --from=ghcr.io/ggml-org/llama.cpp:server-cuda12-b8967 /app/*.so /usr/local/bin/
RUN echo "/usr/local/bin" > /etc/ld.so.conf.d/llama.conf && ldconfig

WORKDIR /app
USER appuser
