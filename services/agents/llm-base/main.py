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
    * `generate()` Modal Cls method (RPC) — text + vision (mmproj engages
      when `images` kwarg is passed) + grammar-level JSON enforcement when
      `format="json"`. Single OpenAI-compat code path via /v1/chat/completions.
    * `fastapi()` ASGI for /v1/embed, /v1/embed_batch, /v1/health.
      The health endpoint combines llama-server + BGE liveness; 503 on degrade.

Deploy:
    PYTHONUTF8=1 modal deploy services/agents/llm-base/main.py

Populate model (one-time, ~30-40min on first run):
    PYTHONUTF8=1 modal run services/agents/llm-base/main.py::download_model

Why PYTHONUTF8=1 on Windows: the Modal CLI reads Dockerfile as cp949 by
default and chokes on UTF-8 sequences (see deployment README §흔한 실패).
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import modal
from pydantic import BaseModel


# Gemma 4 vision-mode chat-template leak. `enable_thinking=False` +
# `reasoning_format=none` strip the <think> trace in text mode, but the vision
# branch of the peg-gemma4 chat template still emits a leading channel/role
# tag pair (e.g. `<|channel>thought<|channel|>` or `<|channel|>thought
# <|message|>`) that bleeds into `content`. Pattern + rationale ported from
# auto_workflow_demo/AI_Agent/app/backends/llamacpp_gemma.py (validated
# 2026-05-06 in vision smoke). Match only at the very start so real content
# containing angle brackets stays intact.
_CHANNEL_LEAK_PREFIX_RE = re.compile(
    r"^(?:<\|?[A-Za-z_]+\|?>[A-Za-z_\s]*<\|?[A-Za-z_]+\|?>)+\s*",
)


def _strip_channel_leak(text: str) -> str:
    return _CHANNEL_LEAK_PREFIX_RE.sub("", text, count=1)


# FastAPI body models must live at module scope. Defining them inside the
# `fastapi()` closure trips FastAPI 0.115+ / Pydantic 2.13's ForwardRef
# resolver and the route raises 500 PydanticUserError at request time.
class EmbedReq(BaseModel):
    text: str


class EmbedBatchReq(BaseModel):
    texts: list[str]


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

        # `--reasoning-format none` disables llama.cpp's reasoning extraction —
        # otherwise the peg-gemma4 chat template routes the entire response to
        # `reasoning_content` and `content` ends up empty, which silently
        # defeats JSON grammar enforcement (response_format only constrains
        # `content`). With `none`, all output lands in `content` and the
        # grammar-level JSON constraint binds correctly. Supported in
        # llama.cpp b8800+ (we ship b8967).
        cmd = [
            "/usr/local/bin/llama-server",
            "--model", MODEL_PATH,
            "--mmproj", MMPROJ_PATH,
            "--host", "127.0.0.1",
            "--port", str(LLAMA_SERVER_PORT),
            "--n-gpu-layers", os.environ.get("N_GPU_LAYERS", "999"),
            "--ctx-size", os.environ.get("CTX_SIZE", DEFAULT_CTX_SIZE),
            "--reasoning-format", "none",
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
        """Gemma 4 completion (text + optional vision). Returns {"generated_text": str}.

        Always routes through llama-server's OpenAI-compatible
        /v1/chat/completions endpoint so the mmproj projector is engaged
        whenever images are supplied — Gemma 4 is a vision model and we want
        a single code path for both modalities.

        kwargs:
            max_tokens (int, default 512)
            temperature (float, default 0.1). Gemma 4 instruction-tuned weights
                run a strong internal "thinking" pass via the peg-gemma4 chat
                template. At the upstream default of 0.7 the thinking section
                tends to consume the entire output budget and the visible
                answer ends up empty. We default to 0.1 (validated against
                Gemma 4 26B-A4B in the auto_workflow_demo harness) which
                keeps thinking short and lets the final answer land in
                `content`. JSON mode (`format="json"`) overrides to 0.0.
            format ("json"): enforce JSON output. Combined with `json_schema`
                kwarg (or default {"type": "object"}), llama.cpp constrains
                generation at the grammar level — output is always parseable.
                Note: Gemma 4 was trained on JSON-shaped documents, not XML,
                so structured prompts/payloads should be JSON (callers'
                responsibility) — passing XML elicits frequent drift.
            json_schema (dict): JSON schema for structured output (used when
                format="json"). Sub-agent generate_structured passes
                `schema.model_json_schema()` here.
            images (list[str]): data URLs (e.g. "data:image/png;base64,...")
                or http(s) URLs. Each becomes an image_url content block
                in the user message — Gemma 4 multimodal path.
            system (str): optional system prompt prepended as a system message.
        """
        # Build OpenAI-compat messages. Image content blocks engage the mmproj
        # projector; text-only path stays a simple string content.
        images = kwargs.get("images") or []
        if images:
            content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
            for url in images:
                content.append({"type": "image_url", "image_url": {"url": url}})
            user_msg: dict[str, object] = {"role": "user", "content": content}
        else:
            user_msg = {"role": "user", "content": prompt}

        messages: list[dict[str, object]] = []
        system = kwargs.get("system")
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(user_msg)

        # Default temperature 0.1 (not the OpenAI 0.7) suppresses Gemma 4's
        # internal thinking pass; see docstring for the rationale.
        is_json_mode = kwargs.get("format") == "json"
        temperature = float(kwargs.get("temperature", 0.0 if is_json_mode else 0.1))

        body: dict[str, object] = {
            "model": "gemma",
            "messages": messages,
            "max_tokens": int(kwargs.get("max_tokens", 512)),
            "temperature": temperature,
            # Kill Gemma 4's hidden reasoning trace. Without these, the chat-
            # template parser strips <think>...</think> from `content` but
            # the model still spends 1500-3700 tokens generating it (prior
            # project's policy_extract smoke 2026-05-06: 76s wall, 3832
            # generated tokens, 165 visible). For structured JSON tasks
            # reasoning produces zero value and breaks grammar enforcement.
            # We set both knobs so whichever the running llama-server build
            # understands wins; the other is ignored. Matches the validated
            # auto_workflow_demo configuration.
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_format": "none",
        }

        # JSON 강제 — llama.cpp grammar-level constraint. If the caller
        # didn't pass an explicit schema we fall back to {"type":"object"}
        # which guarantees parseable JSON without constraining the shape.
        if is_json_mode:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": kwargs.get("json_schema") or {"type": "object"},
                    "strict": True,
                },
            }

        r = self._http.post(
            f"http://127.0.0.1:{LLAMA_SERVER_PORT}/v1/chat/completions",
            json=body,
        )
        r.raise_for_status()
        body_json = r.json()
        # With enable_thinking=False + reasoning_format=none the visible answer
        # lands on `content`. We keep `reasoning_content` as a defensive
        # fallback in case a future llama.cpp build silently ignores both
        # knobs. Vision-mode responses additionally carry a leading channel-
        # tag prefix that the chat-template parser leaves in place — strip it
        # before returning.
        message = body_json.get("choices", [{}])[0].get("message", {})
        raw = message.get("content") or message.get("reasoning_content") or ""
        return {"generated_text": _strip_channel_leak(raw)}

    # --- Embedding ASGI (EmbeddingPort contract) --------------------------
    @modal.asgi_app()
    def fastapi(self):
        import httpx
        from fastapi import Body, FastAPI, HTTPException

        api = FastAPI(title="llm-base", version="1.0")

        @api.get("/v1/health")
        def health() -> dict[str, object]:
            """Combined health — both llama-server and BGE must be ready.

            Sub-agents poll this to detect runtime degrade. Returns 200 only
            when both subsystems answer; otherwise raises so the body returns
            a 503 with the failing component named.
            """
            llm_ok = False
            llm_err: str | None = None
            try:
                r = self._http.get(
                    f"http://127.0.0.1:{LLAMA_SERVER_PORT}/health", timeout=2.0
                )
                llm_ok = r.status_code == 200
                if not llm_ok:
                    llm_err = f"llama-server returned {r.status_code}"
            except httpx.HTTPError as exc:
                llm_err = f"llama-server unreachable: {exc!r}"

            embed_ok = self._bge is not None
            embed_err = None if embed_ok else "BGE-M3 not loaded"

            if not (llm_ok and embed_ok):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "status": "degraded",
                        "llm": {"ok": llm_ok, "error": llm_err},
                        "embed": {"ok": embed_ok, "error": embed_err},
                    },
                )

            return {
                "status": "ok",
                "model_llm": "gemma-4-26B-A4B (multimodal)",
                "model_embed": "bge-m3",
            }

        # Body(...) must be explicit on FastAPI 0.115+ when the BaseModel
        # subclass is defined inside the route closure — without it FastAPI
        # treats the param as a query string and returns 422.
        @api.post("/v1/embed")
        def embed(req: EmbedReq = Body(...)) -> dict[str, list[float]]:
            vec = self._bge.encode([req.text], normalize_embeddings=True)
            return {"embedding": vec[0].tolist()}

        @api.post("/v1/embed_batch")
        def embed_batch(req: EmbedBatchReq = Body(...)) -> dict[str, list[list[float]]]:
            vecs = self._bge.encode(req.texts, normalize_embeddings=True)
            return {"embeddings": [v.tolist() for v in vecs]}

        return api
