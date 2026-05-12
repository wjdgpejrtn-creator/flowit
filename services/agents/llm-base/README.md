# llm-base — Modal app 배포 가이드

> **REQ-004 §2.3 + REQ-011** — Gemma 4 26B-A4B (llama.cpp) + BGE-M3 (sentence-transformers) 단일 L4 colocation. 4개 sub-agent Modal app(orchestrator / agent-composer / agent-skills-builder / agent-personalization)이 본 `llm-base`를 `ModalLLMAdapter` (RPC) / `ModalEmbeddingAdapter` (HTTP)로 호출한다.
>
> 2026-04-24 GCP → Modal 피벗 결정 (Cloud Run GPU 쿼터 + GCE L4 capacity 둘 다 차단). 자세한 결정 이력: `docs/context/decisions.md` ADR-022.

## 사전 체크

- [ ] Modal 계정 + 토큰 (`pip install modal && modal token new`)
- [ ] HuggingFace `HF_TOKEN` (Gemma 4 라이선스 수락 후 read 토큰)
- [ ] Python 환경: `modal` 설치된 venv
- [ ] Windows: `PYTHONUTF8=1` 환경 변수 필수 (modal CLI cp949 이슈)

## 1. Modal Secrets 등록 (1회)

```bash
# HuggingFace read token (rate-limit 회피)
modal secret create huggingface-token HF_TOKEN=hf_xxx
```

향후 LangSmith 트레이싱이 필요하면 별도로:

```bash
modal secret create langsmith-api-key LANGCHAIN_API_KEY=ls_xxx
```

## 2. Modal Volume 모델 다운로드 (1회)

```bash
PYTHONUTF8=1 modal run services/agents/llm-base/main.py::download_model
```

첫 실행은 ~30-40min (이미지 빌드 + HF 다운로드 16.9 GiB). 이후 cold start는 Volume 마운트만으로 즉시 접근. Volume 이름: `llm-base-models`.

## 3. Modal Deploy

```bash
PYTHONUTF8=1 modal deploy services/agents/llm-base/main.py
```

출력에 ASGI endpoint URL 표시:
`https://<workspace>--llm-base-llmbase-fastapi.modal.run`

대시보드: https://modal.com/apps/<workspace>/main/deployed/llm-base

## 4. 호출 계약 (sub-agent들이 이 형태로 부른다)

### 4.1 LLM — Modal RPC

llama-server의 OpenAI-compatible `/v1/chat/completions`를 단일 경로로 사용합니다. text-only / 비전 / JSON 강제 모두 같은 RPC.

```python
import modal

cls = modal.Cls.from_name("llm-base", "LLMBase")

# (1) 기본 텍스트
result = await cls().generate.remote.aio(
    prompt="요약해줘: ...",
    max_tokens=512,
    temperature=0.7,
)
# → {"generated_text": "..."}

# (2) JSON 강제 — grammar-level constraint, 응답 무조건 parseable
result = await cls().generate.remote.aio(
    prompt="다음 문서에서 정책 카드를 추출:\n...",
    format="json",
    json_schema={
        "type": "object",
        "properties": {
            "skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "condition": {"type": "string"},
                        "action": {"type": "string"},
                    },
                    "required": ["id", "name", "condition", "action"],
                },
            },
        },
        "required": ["skills"],
    },
)
# → {"generated_text": '{"skills":[{"id":"SK-001",...}]}'} — JSON parse 100% 성공

# (3) 비전 (Gemma 4 multimodal, mmproj projector 자동 engage)
result = await cls().generate.remote.aio(
    prompt="이 화면에서 사용자가 보고 있는 워크플로우 노드들을 나열해줘.",
    images=["data:image/png;base64,iVBORw0KG..."],  # data URL or http(s) URL
    max_tokens=512,
)

# (4) system prompt + 모든 옵션 조합
result = await cls().generate.remote.aio(
    prompt="...",
    system="You are concise.",
    images=[...],
    format="json",
    json_schema={...},
    max_tokens=1024,
    temperature=0.0,
)
```

> ⚠️ **PR #39 ModalLLMAdapter 후속 패치 필요**:
> 현재 어댑터는 `modal.Function.lookup("llm-base", "generate")` 패턴인데,
> `generate`는 cls method라 `modal.Cls.from_name("llm-base", "LLMBase")` 패턴이 정답.
> 이 README 작성 시점 기준 adapter 후속 PR로 정정 필요.

### 4.2 Embedding — HTTP

```python
import httpx

base = "https://<workspace>--llm-base-llmbase-fastapi.modal.run"

# 단일
r = httpx.post(f"{base}/v1/embed", json={"text": "..."})
# → {"embedding": [1024 floats]}

# 배치
r = httpx.post(f"{base}/v1/embed_batch", json={"texts": ["...", "..."]})
# → {"embeddings": [[1024 floats], [1024 floats]]}

# health
r = httpx.get(f"{base}/v1/health")
# → {"status": "ok", "model_llm": "gemma-4-26B-A4B", "model_embed": "bge-m3"}
```

> ⚠️ **PR #39 ModalEmbeddingAdapter 주석 정정 필요**:
> `BGE-M3 단일 문장 임베딩 ... 768차원` 주석은 잘못된 정보. BGE-M3는 **1024차원**.
> Pgvector 테이블 정의 `VECTOR(1024)` 와 정합.

### 4.3 환경 변수 (sub-agent 컨테이너에 주입)

| 변수명 | 값 | 사용처 |
|---|---|---|
| `LLM_BASE_URL` | (Modal RPC 사용 시 미사용, 헬스체크용으로만 보관) | composer/orchestrator/skills_builder/personalization |
| `EMBEDDING_BASE_URL` | `https://<workspace>--llm-base-llmbase-fastapi.modal.run` | composer/personalization |
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` | Modal workspace 토큰 | 전체 sub-agent |

`MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`는 `modal.Cls.from_name` 호출 시 자동 사용된다 (Modal SDK가 환경변수에서 읽음).

## 5. Smoke Test

```bash
URL="https://<workspace>--llm-base-llmbase-fastapi.modal.run"

# health — 인증 불필요. llama-server + BGE 둘 다 살아있어야 200, 하나라도 죽으면 503
curl -sS -m 300 "$URL/v1/health"
# 정상 기대: {"status":"ok","model_llm":"gemma-4-26B-A4B (multimodal)","model_embed":"bge-m3"}
# 디그레이드: HTTP 503 + {"status":"degraded","llm":{"ok":false,"error":"..."},"embed":{...}}

# embed
curl -sS -m 300 -H "Content-Type: application/json" \
  -d '{"text":"refund policy: escalate over $500"}' \
  "$URL/v1/embed" | python -c "import sys,json; d=json.load(sys.stdin); print(len(d['embedding']))"
# 기대: 1024

# generate via Modal RPC
modal run -- python -c "
import asyncio, modal
async def main():
    cls = modal.Cls.from_name('llm-base', 'LLMBase')
    r = await cls().generate.remote.aio(prompt='Say hi in one word.', max_tokens=8)
    print(r)
asyncio.run(main())
"
```

첫 호출은 cold start 1-3min (image pull + volume mount + model mmap). 이후 warm 상태에서 P95 ≤ 8s (256 토큰 기준, spec §비기능 제약).

## 6. 비용 관리

- L4 in-use: ~$0.59/hr (per-second 과금)
- Modal Volume: 16.9 GiB × $0.15/GB·mo ≈ **$2.5/mo**
- `scaledown_window=300` (5분 idle 후 종료). 단발 요청만이면 ≈ 5min/call billable
- 데모/개발용 ~30hr/월 사용 시 예상 월간 **$20-30**

## 7. 흔한 실패 패턴

| 증상 | 원인 | 조치 |
|---|---|---|
| `UnicodeDecodeError: 'cp949'` on Windows | modal CLI가 Dockerfile UTF-8을 cp949로 읽음 | `PYTHONUTF8=1` prefix 필수 |
| `ERROR: model not found at /vol/...` + Runner failed | Dockerfile ENTRYPOINT가 container 부팅 차단 | `main.py`의 `.dockerfile_commands(["ENTRYPOINT []"])` 확인 |
| `libgomp.so.1: cannot open shared object file` | CUDA runtime 이미지에 OpenMP 런타임 없음 | `Dockerfile` `apt-get install libgomp1` 확인 |
| `unknown model architecture: 'gemma4'` | llama.cpp가 Gemma 4 지원 전 빌드 | Dockerfile `llama.cpp:server-cuda12-b8967` (b8860+) 확인 |
| `load_backend: failed to load <dir>: Is a directory` | ggml plugin loader에 디렉토리 전달 | `GGML_BACKEND_PATH` 환경 변수 설정 금지 (Dockerfile은 ldconfig만 사용) |
| Multi-stage cache가 stale binary 반환 | Modal 캐시 quirk | `main.py`에서 `force_build=True` 한 번 켜고 deploy, 성공 후 제거 |
| cold start가 매번 3분+ | 이미지 pull이 GPU 노드마다 발생 (~5GB) | `scaledown_window` 늘리거나 `min_containers=1` (비용↑) |

## 8. 롤백 / 정리

```bash
modal app stop llm-base
modal volume delete llm-base-models  # 주의: 다음 deploy 시 download_model 재실행 (16.9 GiB 재다운로드)
modal secret delete huggingface-token
```

## 9. 다음 단계 (본 README 범위 외)

- **4개 sub-agent Modal app 배포**: orchestrator, agent-composer, agent-skills-builder, agent-personalization. 각각 `services/agents/{name}/main.py` 형태로 작성 (담당자별).
- **PR #39 어댑터 정정**: `modal.Function.lookup` → `modal.Cls.from_name` + 임베딩 주석 768→1024 차원 수정 (별도 후속 PR).
- **Inter-agent VPC 통신**: spec §4.3 옵션 C (VPC 내부 only, 외부 차단). Modal workspace 공유로 자동 충족.
