"""llm-base — Modal app for Gemma 4 26B-A4B + BGE-M3 (REQ-004 §2.3 + REQ-011).

LLM (Gemma 4 GGUF on llama.cpp) and embedding (BGE-M3) are colocated on a
single L4 GPU. The colocation VRAM budget was validated on 2026-04-30 against
the same image stack (ADR-022 risk 1-B closed by validate_bge_gemma harness).

Layout:
- `image`: built from services/agents/llm-base/Dockerfile. The llama-server
  binary is COPYed from `ghcr.io/ggml-org/llama.cpp:server-cuda12-b8967`
  (Ubuntu 24.04 + CUDA 12.8 — must match the upstream image to keep
  glibc/libstdc++ ABIs aligned). Gemma 4 support requires llama.cpp b8860+.
- `model_volume`: persistent Modal Volume holding the 16.9 GiB GGUF + mmproj.
  Populated once via `modal run main.py::download_model`.
- `LLMBase`: @cls with @enter() boots llama-server subprocess + loads BGE-M3
  weights onto the same L4. Exposes:
    * `generate()` as a Modal Cls method (RPC) for LLMPort
    * `fastapi()` ASGI for /v1/embed, /v1/embed_batch, /v1/health (EmbeddingPort)

Deploy:
    PYTHONUTF8=1 modal deploy services/agents/llm-base/main.py

Populate model (one-time, ~30-40min on first run):
    PYTHONUTF8=1 modal run services/agents/llm-base/main.py::download_model

Why PYTHONUTF8=1 on Windows: the Modal CLI reads Dockerfile as cp949 by
default and chokes on UTF-8 sequences (see deployment README §흔한 실패).
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import modal

APP_NAME = "llm-base"
MODEL_REPO = "unsloth/gemma-4-26B-A4B-it-GGUF"
MODEL_FILE = "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf"
MMPROJ_FILE = "mmproj-F16.gguf"
MODEL_DIR = "/vol"
MODEL_PATH = f"{MODEL_DIR}/{MODEL_FILE}"
MMPROJ_PATH = f"{MODEL_DIR}/{MMPROJ_FILE}"
BGE_MODEL = "BAAI/bge-m3"
LLAMA_SERVER_PORT = 8080
DEFAULT_CTX_SIZE = "8192"

image = (
    modal.Image.from_dockerfile(
        path="services/agents/llm-base/Dockerfile",
        context_dir=".",
    )
    .pip_install(
        "huggingface_hub>=0.24",
        # BGE-M3 — 1024-dim embeddings. ~2 GB weights cached on first call.
        "sentence-transformers>=3.0",
        "torch>=2.6",
        # FastAPI for /v1/embed ASGI endpoint
        "fastapi>=0.115",
        "httpx>=0.27",
    )
    .env({
        "MODEL_PATH": MODEL_PATH,
        "LLAMA_SERVER_URL": f"http://127.0.0.1:{LLAMA_SERVER_PORT}",
    })
    # The Dockerfile's ENTRYPOINT runs entrypoint.sh which checks MODEL_PATH —
    # that blocks every Modal container start including download_model (which
    # is supposed to populate the volume). Clear the inherited ENTRYPOINT so
    # Modal's Python entrypoint runs cleanly.
    .dockerfile_commands(["ENTRYPOINT []"])
)

model_volume = modal.Volume.from_name("llm-base-models", create_if_missing=True)
hf_secret = modal.Secret.from_name("huggingface-token")

app = modal.App(APP_NAME)


@app.function(
    image=image,
    volumes={MODEL_DIR: model_volume},
    secrets=[hf_secret],
    timeout=3600,
)
def download_model() -> None:
    """One-shot HF → Modal Volume populator. Idempotent.

    Run once after first deploy; subsequent cold starts mmap from the volume.
    Re-running with the files already present is a no-op.
    """
    from huggingface_hub import hf_hub_download

    Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)
    token = os.environ.get("HF_TOKEN") or None

    for filename, target in [(MODEL_FILE, MODEL_PATH), (MMPROJ_FILE, MMPROJ_PATH)]:
        if Path(target).exists():
            size_gb = Path(target).stat().st_size / 1e9
            print(f"[skip] {target} present ({size_gb:.1f} GB)")
            continue
        print(f"downloading {MODEL_REPO}/{filename} → {target}")
        hf_hub_download(
            repo_id=MODEL_REPO,
            filename=filename,
            local_dir=MODEL_DIR,
            token=token,
        )
        size_gb = Path(target).stat().st_size / 1e9
        print(f"done — {size_gb:.1f} GB")

    model_volume.commit()
    print("volume committed")


@app.cls(
    image=image,
    gpu="L4",
    volumes={MODEL_DIR: model_volume},
    secrets=[hf_secret],
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=4)
class LLMBase:
    """Gemma 4 (llama.cpp subprocess) + BGE-M3 (in-process) on one L4."""

    @modal.enter()
    def boot(self) -> None:
        import httpx
        from sentence_transformers import SentenceTransformer

        for required in (MODEL_PATH, MMPROJ_PATH):
            if not Path(required).exists():
                raise FileNotFoundError(
                    f"Required GGUF missing at {required}. Run "
                    "`modal run services/agents/llm-base/main.py::download_model` first."
                )

        cmd = [
            "/usr/local/bin/llama-server",
            "--model", MODEL_PATH,
            "--mmproj", MMPROJ_PATH,
            "--host", "127.0.0.1",
            "--port", str(LLAMA_SERVER_PORT),
            "--n-gpu-layers", os.environ.get("N_GPU_LAYERS", "999"),
            "--ctx-size", os.environ.get("CTX_SIZE", DEFAULT_CTX_SIZE),
        ]
        self._proc = subprocess.Popen(cmd)

        # Model mmap takes 30-60s on warm volume, longer on first boot.
        deadline = time.time() + 180
        last_err: Exception | None = None
        ready = False
        while time.time() < deadline:
            try:
                r = httpx.get(
                    f"http://127.0.0.1:{LLAMA_SERVER_PORT}/health", timeout=2.0
                )
                if r.status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError as exc:
                last_err = exc
            time.sleep(1)

        if not ready:
            self._proc.terminate()
            raise RuntimeError(
                f"llama-server not ready in 180s; last error: {last_err}"
            )
        print("llama-server ready")

        # BGE-M3 onto the same L4. ADR-022 §8.5 — total VRAM ≈ Gemma 14 GiB +
        # BGE 1.8 GiB + KV/context ≈ 18 GiB, fits inside L4's 24 GiB.
        self._bge = SentenceTransformer(BGE_MODEL, device="cuda")
        self._http = httpx.Client(timeout=90.0)
        print("BGE-M3 loaded")

    @modal.exit()
    def shutdown(self) -> None:
        if getattr(self, "_proc", None):
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if getattr(self, "_http", None):
            self._http.close()

    # --- LLM RPC (LLMPort contract) ---------------------------------------
    @modal.method()
    def generate(self, prompt: str, **kwargs: object) -> dict[str, str]:
        """Gemma 4 completion. Returns {"generated_text": str}.

        kwargs:
            max_tokens (int, default 512) → llama.cpp n_predict
            temperature (float, default 0.7)
            format ("json"): enforce JSON output via llama.cpp json_schema mode
        """
        body: dict[str, object] = {
            "prompt": prompt,
            "n_predict": int(kwargs.get("max_tokens", 512)),
            "temperature": float(kwargs.get("temperature", 0.7)),
        }
        if kwargs.get("format") == "json":
            # llama.cpp's built-in JSON grammar — guarantees parseable JSON output
            body["json_schema"] = {"type": "object"}

        r = self._http.post(
            f"http://127.0.0.1:{LLAMA_SERVER_PORT}/completion",
            json=body,
        )
        r.raise_for_status()
        return {"generated_text": r.json().get("content", "")}

    # --- Embedding ASGI (EmbeddingPort contract) --------------------------
    @modal.asgi_app()
    def fastapi(self):
        from fastapi import FastAPI
        from pydantic import BaseModel

        api = FastAPI(title="llm-base", version="1.0")

        class EmbedReq(BaseModel):
            text: str

        class EmbedBatchReq(BaseModel):
            texts: list[str]

        @api.get("/v1/health")
        def health() -> dict[str, str]:
            return {"status": "ok", "model_llm": "gemma-4-26B-A4B", "model_embed": "bge-m3"}

        @api.post("/v1/embed")
        def embed(req: EmbedReq) -> dict[str, list[float]]:
            vec = self._bge.encode([req.text], normalize_embeddings=True)
            return {"embedding": vec[0].tolist()}

        @api.post("/v1/embed_batch")
        def embed_batch(req: EmbedBatchReq) -> dict[str, list[list[float]]]:
            vecs = self._bge.encode(req.texts, normalize_embeddings=True)
            return {"embeddings": [v.tolist() for v in vecs]}

        return api
