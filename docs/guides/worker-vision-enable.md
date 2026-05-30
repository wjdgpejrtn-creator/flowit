# 워커 vision(InterleavingParser) 활성화 가이드

문서 분석(`analyze_document_task`)에서 Gemma 4 멀티모달 vision 추출을 켜는 절차.
**워커 쪽 코드 seam은 이미 깔려 있다**(`document_tasks._build_vision_llm` → `HttpVisionLLM`).
이 문서는 나머지(크로스 모듈 2곳 + 토글)를 정리한다.

## 전송 방식: HTTP (Modal 토큰 불필요)

worker는 이미 `LLM_BASE_URL`(llm-base web endpoint) env를 secret_env_vars로 갖고 있다.
그래서 vision도 **HTTP로** 호출한다 — **Modal 토큰/secret/terraform 전부 불필요**.

```
요청 : POST {LLM_BASE_URL}/v1/generate
        {"prompt": str, "images": [data_url, ...], "max_tokens": int, "temperature": float}
응답 : {"generated_text": str, "finish_reason": str, "usage": {...}}
```

## 현재 상태 (seam 깔린 후)

- `_build_pipeline()`이 `ParserFactory(llm=_build_vision_llm())`로 조립.
- `_build_vision_llm()`은 **기본 None**(텍스트 전용, 현 동작). `DOC_PARSER_VISION_ENABLED`가
  켜지고 `LLM_BASE_URL`이 있으면 `HttpVisionLLM(base_url)`을 반환. 누락/실패 시 경고 후 None degrade.
- `HttpVisionLLM.generate(prompt, **kwargs)` → `POST {LLM_BASE_URL}/v1/generate`.

## 켜는 절차

### 1. llm-base HTTP에 `images` 패스스루 (정혜님/REQ-011)
llm-base `_run_generate`는 `images` kwargs를 **이미 처리**한다(Gemma 4 vision, `main.py:298`).
그러나 HTTP `GenerateReq`에 `images` 필드가 없어 `generate_http`가 전달하지 못한다. 추가:
```python
class GenerateReq(BaseModel):
    prompt: str
    images: list[str] = []          # ← 추가 (data URL 목록)
    ...
# generate_http 안:
    kwargs["images"] = req.images   # ← 추가
```
> Modal RPC 경로(`generate.remote(images=...)`)는 이미 동작하므로, 본 변경은 HTTP 경로 전용.

### 2. VisionExtractor를 plain call로 (쿠쿠/REQ-006)
`vision_extractor.py`의 Modal 전용 호출을 transport-agnostic로:
```python
result = self._llm.generate(            # ← .generate.remote( 에서 .remote 제거
    prompt, images=[data_url], max_tokens=1024, temperature=0.1,
)
return result.get("generated_text", "").strip() or None
```
주입되는 `llm`(worker의 `HttpVisionLLM`)이 `.generate(prompt, images=..., **kwargs) -> dict`를
제공한다. 응답 키 `generated_text`는 동일.
+ (별개) `page_count`를 `file_meta`에 써넣어 `coverage.total_pages` 0 버그 해소.

### 3. vision 토글 (황대원/REQ-007)
worker `env_vars`에 `DOC_PARSER_VISION_ENABLED = "true"` 추가(terraform 또는 Cloud Run revision env).
`LLM_BASE_URL`은 worker `secret_env_vars`에 이미 매핑돼 있어 추가 작업 없음.

## 주의 (성능/비용/타임아웃)
- vision은 **페이지(이미지)당 Gemma 4 GPU inference** — 텍스트 추출 대비 느림 + 비용↑.
- 프론트 폴링 타임아웃이 **60초**(`documents/[id]/page.tsx` `POLL_TIMEOUT_MS`)다. 페이지 많은
  문서는 60초 초과 가능 → 프론트는 안내 후에도 워커는 계속 돌아 완료 시 다음 새로고침에 반영.
  vision 상시화 시 폴링 타임아웃 상향 검토. `HttpVisionLLM` 타임아웃 기본 120초.
- L4 24/7 비용 주의([[modal_keep_warm_cost]]) — vision 트래픽 늘면 llm-base 스케일/비용 재산정.

## 검증 (켠 뒤)
1. 워커 로그에 `vision LLM 활성 — HTTP <url>/v1/generate`.
2. PDF 분석 → `coverage.vision_blocks > 0`(DB `documents.coverage`) + 프론트 커버리지 스트립에
   "이미지 N" 표시.
3. 토큰/플래그 끄면 즉시 텍스트 전용으로 복귀(안전 degrade).
