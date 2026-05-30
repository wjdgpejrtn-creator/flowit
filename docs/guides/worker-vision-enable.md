# 워커 vision(InterleavingParser) 활성화 가이드

문서 분석(`analyze_document_task`)에서 Gemma 4 멀티모달 vision 추출을 켜는 절차.
**워커 쪽 코드 seam은 이미 깔려 있다**(`document_tasks._build_vision_llm`). 이 문서는
나머지(인프라 + 크로스 모듈 확인 + 토글)를 정리한다.

## 현재 상태 (seam 깔린 후)

- `_build_pipeline()`이 `ParserFactory(llm=_build_vision_llm())`로 조립.
- `_build_vision_llm()`은 **기본 None**(텍스트 전용, 현 동작). 아래 env가 모두 갖춰질 때만
  llm-base Modal Cls 인스턴스를 반환해 vision을 켠다. 설정 누락/생성 실패 시 경고 후 None degrade.
- doc_parser `VisionExtractor`는 `llm.generate.remote(prompt, images=[data_url])`(Modal RPC)로
  호출 → llm은 **llm-base Modal Cls 인스턴스**여야 한다.
- llm-base `_run_generate(prompt, **kwargs)`는 이미 `images` kwargs를 처리(Gemma 4 vision).
  → **HTTP `GenerateReq`엔 images 필드가 없지만**, VisionExtractor는 HTTP가 아니라 Modal RPC를
  쓰므로 무관(정혜님 HTTP DTO 수정 불필요).

## 켜는 절차

### 0. (확인) `modal` 패키지 — 워커 이미지에 이미 포함
`document_tasks._build_vision_llm()`이 `import modal`을 한다. **이미 워커 이미지에 설치돼
있다**: doc_parser(`modal>=0.73`, #239로 워커 Dockerfile이 설치) + execution_engine
`[worker]` extra가 명시 선언. → 별도 설치 단계 불필요. (만약 `import modal` 실패하면 seam이
경고 후 None degrade하므로 vision이 silent off된다 — 이 경우 워커 이미지의 modal 설치부터 점검.)

### 1. Modal 토큰 secret 신설 (infra — 황대원)
VisionExtractor의 `.generate.remote()`는 Modal 클라이언트 인증을 요구한다. 현재 어떤 Cloud Run
서비스에도 Modal 토큰이 없다(Secret Manager에 `huggingface-token`만). 공용 Modal 토큰
(팀 `.env` 공유분, [[modal_shared_token]])을 secret으로 등록:

```bash
echo -n "<MODAL_TOKEN_ID>"     | gcloud secrets create modal-token-id     --data-file=- --project=<GCP_PROJECT_ID>
echo -n "<MODAL_TOKEN_SECRET>" | gcloud secrets create modal-token-secret --data-file=- --project=<GCP_PROJECT_ID>
```
> 토큰 값은 `.env`/`~/.modal.toml` 보유자(황대원)만 주입. 코드/PR에 값 노출 금지.

### 2. 워커에 secret_env_vars 매핑 (terraform — 황대원)
`infra/terraform/envs/staging/main.tf` 워커 모듈 `secret_env_vars`에 추가:
```hcl
MODAL_TOKEN_ID     = { secret_id = "modal-token-id",     version = "latest" }
MODAL_TOKEN_SECRET = { secret_id = "modal-token-secret", version = "latest" }
```
+ `variables.tf`의 `agent_secret_names`(accessor 부여 목록)에 두 secret 추가 → `terraform apply`.
worker SA가 두 secret accessor를 갖게 한 뒤 워커 재배포.

### 3. vision 토글 (env — 황대원)
워커 `env_vars`에 `DOC_PARSER_VISION_ENABLED = "true"` 추가(또는 Cloud Run revision env).
선택 override: `LLM_BASE_MODAL_APP`(기본 `llm-base`), `LLM_BASE_MODAL_CLS`(기본 `LLMBase`).

### 4. 크로스 모듈 확인
- **쿠쿠(doc_parser/REQ-006)**: `InterleavingParser`/`VisionExtractor`/`TableDetector`가 실제
  llm-base 응답(`result.get("generated_text")`)으로 ContentBlock을 만드는지 + `page_count`를
  `file_meta`에 써넣어 `coverage.total_pages`가 채워지는지(현재 0 버그) 확인.
- **정혜님(llm-base/REQ-011)**: `LLMBase.generate.remote(prompt, images=[...])`가 Gemma 4 vision
  추론을 실제 수행하는지(이미지 data_url 입력 처리) smoke 확인. 현재 텍스트 smoke만 검증됨.

## 주의 (성능/비용/타임아웃)
- vision은 **페이지(이미지)당 Gemma 4 Modal GPU RPC** — 텍스트 추출 대비 느림 + 비용↑.
- 프론트 폴링 타임아웃이 **60초**(`documents/[id]/page.tsx` `POLL_TIMEOUT_MS`)다. 페이지 많은
  문서는 60초 초과 가능 → 프론트가 "60초 초과" 안내 후에도 워커는 계속 돌아 완료되면 다음
  새로고침에 반영됨. vision 상시화 시 폴링 타임아웃 상향 검토.
- L4 24/7 비용 주의([[modal_keep_warm_cost]]) — vision 트래픽 늘면 llm-base 스케일/비용 재산정.

## 검증 (켠 뒤)
1. 워커 로그에 `vision LLM 활성 — Modal RPC llm-base/LLMBase`.
2. PDF 분석 → `coverage.vision_blocks > 0` (DB `documents.coverage`) + 프론트 커버리지 스트립에
   "이미지 N" 표시.
3. 토큰/플래그 끄면 즉시 텍스트 전용으로 복귀(안전 degrade).
