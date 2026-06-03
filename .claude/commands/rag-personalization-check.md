REQ-004 personalization RAG 파이프라인의 골든 스냅샷이 그대로 유효한지 결정적으로 점검한다. 인자 없음. (글로벌 개인 커맨드 `/rag-check`는 다른 프로젝트(VOD 추천) 잔재이므로 혼동 금지 — 이 레포 personalization RAG 점검은 이 커맨드를 쓴다.)

---

## 무엇을 점검하나

`modules/ai_agent/tests/eval/rag_personalization/snapshots/bge_m3_embeddings.json`(실제 BGE-M3로 1회 캡처한 골든 스냅샷)만 읽어, Modal·GCS·DB 어디에도 붙지 않고 4가지를 assert한다:

1. **스냅샷 로드** — corpus 6 / queries 7 패턴이 전부 캡처돼 있는가
2. **768차원 assert** — 모든 벡터가 정확히 768차원인가 (프로젝트 전역 임베딩 차원 SSOT: BGE-M3 1024→Matryoshka 768 절단, pgvector `vector(768)`)
3. **코사인 sanity** — 정답 분리대가 살아 있는가: 정답(primary) 코사인 ≥ 0.50, distractor 최고 < 0.45, `min(primary) > max(distractor)` (마진 분석 관측: 정답 0.553~0.754 / distractor 0.372)
4. **시드 왕복** — `InMemoryPersonalMemoryStore` save→load 가 동일 벡터를 돌려주는가

> 이 점검은 capture/스윕을 **재실행하지 않는다.** 스냅샷이 깨지거나 재캡처로 분리대가 무너졌을 때만 빨갛게 잡는 회귀 가드다.

---

## 실행 절차

1. 스냅샷 점검기를 돌린다 (Windows 콘솔 cp949에서 ∅ 등 유니코드 출력으로 죽지 않도록 UTF-8 강제 + 모듈 import 경로 지정):

```powershell
$env:PYTHONUTF8=1; $env:PYTHONIOENCODING="utf-8"; $env:PYTHONPATH="modules;packages/common_schemas/python"; python -m ai_agent.tests.eval.rag_personalization.check_snapshot
```

(bash/CI라면: `PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONPATH="modules:packages/common_schemas/python" python -m ai_agent.tests.eval.rag_personalization.check_snapshot`)

2. 이어서 정식 회귀 테스트(스모크 2 + 골든 8)도 같이 돌려 배선까지 확인한다:

```powershell
$env:PYTHONUTF8=1; $env:PYTHONIOENCODING="utf-8"; $env:PYTHONPATH="modules;packages/common_schemas/python"; python -m pytest modules/ai_agent/tests/eval -q
```

---

## 결과 해석

- **둘 다 통과(점검기 종료코드 0 + pytest green)** → 스냅샷 유효, RAG 권장값(top_k=3, min_score 0.5)도 그대로. 한 줄로 "스냅샷 유효" 보고.
- **점검기 FAIL** → 어느 검사가 깨졌는지 출력에 라인별로 찍힌다. 768차원/분리대가 깨졌으면 **재캡처 산출물이 의심**되므로 `capture_embeddings.py`를 누가 어떤 엔드포인트로 다시 떴는지부터 확인한다(차원 768 SSOT 위반 여부).
- **pytest skip(골든 8개)** → 스냅샷 파일이 없는 것. `capture_embeddings.py`를 먼저 실행해야 한다(Modal BGE-M3 필요, `EMBEDDING_BASE_URL` 환경변수).

점검 결과는 **채팅에 표로 먼저 요약**하고, 커밋/PR 반영은 사용자가 명시 지시할 때만 한다.
