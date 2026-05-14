# ai_agent (REQ-004) Sprint 3 1주차 Skills Builder 작업 보고서 (2026-05-14)

**작업일**: 2026-05-14 (목)
**담당자**: 박아름 (Skills Builder Agent 분장)
**전일 보고서**: `sprint-3-week1-2026-05-13-skills-builder.md` 참조

---

## 1. 작업 개요

5/13 야간 마감 시점의 박아름 측 차단(ConnectorLoopError 디버깅 5건 모두 실패)이 신정혜님의 PR #56 commit `6390a43` (Connector lazy init + 명시적 loop 바인딩) 패턴으로 풀렸다. 5/14는 PR #56 review fix 반영판 검증 + APPROVE, PR #54 (햄햄 personalization) embedder_port shim 변경 회수 권고, SSOT 결정 3건 협의(health path / SSE 종결 / embedder_port), SSE dual 패턴 박아름 영역 적용까지 진행했다.

박아름 측 진행 가능 작업은 PR #56 머지 대기 중 (Connector 패턴 적용 + Test plan #2/#3 검증 트리거). SSOT 결정은 모두 완료 — 신정혜 SSOT 갱신 PR + 박아름 후속 docs PR로 분산 처리 합의.

세션 분할:

- **오전**: PR #56 review fix 검증 + APPROVE 게시 + 추가 보강 권고 3건 발견 + 신정혜 카톡 답변 결정
- **오후**: PR #54 햄햄 사전 양해 → 박아름 회수 권고 게시 → 햄햄 #4 보류 결정 → 박아름 +1 동의 + 후속 docs PR 약속 → 조장 SSOT 결정 3건 모두 확정
- **저녁**: SSE dual 패턴 박아름 영역 적용 (main.py + integration test 3건 추가, 137/137 통과)

---

## 2. PR #56 review fix 반영판 검증 + APPROVE

### 2.1 신정혜님 commit `9d50311b` 14 insertions 반영 확인

5/13 박아름 보강 5건 중 #2/#3/#4가 commit `9d50311b`에 정확히 반영됨. #1/#5는 후속 PR로 분리 결정.

| # | 5/13 권고 | 이번 반영 | 상태 |
|---|----------|----------|------|
| 1 | `setup_modal_token.py` `os.environ` 토큰 leak | (이번 push 대상 아님) | ⏳ 후속 PR |
| 2 | `/v1/health` `repr(exc)` 노출 | `"database unreachable"`로 detail 마스킹 | ✅ |
| 3 | SSE error 후 done frame 미발송 | composer + orchestrator 양쪽 추가 (dual 종결) | ✅ |
| 4 | ModalEmbeddingAdapter timeout 30s | 30s → **180s** + cold start 주석 | ✅ |
| 5 | `scaledown_window` keep_warm 검토 | (이번 push 대상 아님) | ⏳ 후속 PR |

### 2.2 3축 리뷰 결과 (모두 PASS, 머지 차단 0건)

- **SSOT 정합성** ✅ — `modal_embedding_adapter.py:8`이 `nodes_graph.domain.ports.EmbedderPort` import (REQ-004 spec line 129~131 부합), `AgentProtocolResponse(frames, state_delta, next_action)` 시그니처 정확 일치, `next_action: Literal["continue", "complete", "error"]` 사용 — spec과 동일.
- **타 모듈 의존성** ✅ — `_DEFAULT_TIMEOUT=180.0` 변경 영향: composer / skills-builder / bootstrap_node_definitions.py 자동 적용. 박아름 5/13 임시 패치(`_client.timeout` 직접 180s 교체) 제거 가능. agent-composer composition root에서 `ai_agent + nodes_graph + storage` 모두 import — services 레이어이므로 정상.
- **Clean Architecture** ✅ — `modal_embedding_adapter.py`는 adapter 레이어 + `nodes_graph.EmbedderPort` 구현 — 위치 정확. SSE 직렬화·종결 로직이 composition root에만 있음 — 도메인/UseCase 레이어 침범 없음.

### 2.3 박아름 게시

- **APPROVED 코멘트**: https://github.com/billionaireahreum/Workflow_Automation/pull/56 (billionaireahreum, 2026-05-14 10:02 KST)
- 5/13 보강 5건 반영 대조 + 3축 리뷰 결과 + 추가 보강 권고 3건 동봉

---

## 3. PR #56 추가 보강 권고 3건 발견

3축 리뷰는 PASS이지만 검증 중 새로 발견한 항목 3건. 박아름 영역도 영향받는 cross-cutting 사안이라 즉시 발신.

| # | 권고 | 박아름 작업 의존? | 결정 권한 |
|---|------|------------------|----------|
| A | health path 불일치 — SSOT (`POST /v1/agent/health`) ↔ 코드 (`GET /v1/health`). composer/skills-builder/orchestrator 셋 다 동일 패턴 | ✅ 의존 | 조장 SSOT 결정 |
| B | SSE 종결 패턴 — 신정혜 dual 종결 (error frame + complete frame) ↔ 박아름 single 종결 (`_classify_next_action` ResultFrame→complete / ErrorFrame→error). frontend contract 통일 필요 | ✅ 의존 | 조장 SSOT 명시 (박아름 위임 결정) |
| C | `db_err = repr(exc)` dead code (마스킹 OK이지만 변수 안 씀) | ❌ 무관 | 신정혜 자체 처리 (5/14 수정 완료) |

### 3.1 신정혜 카톡 답변 (오후)

- 권고 A: SSOT 갱신 권장 (GET /v1/health 표준 + 코드 변경 0건). 신정혜 SSOT 갱신 PR로 처리 부탁
- 권고 B: 둘이 정하지 말고 조장 SSOT 명시 요청 권장 (spec drift 재발 방지). 신정혜 SSOT 갱신 PR 안에 조장 멘션해서 두 결정 동시 트리거 부탁
- 권고 C: 신정혜 처리 완료 인정

---

## 4. PR #54 (햄햄 personalization) embedder_port shim 변경 처리

### 4.1 햄햄 사전 카톡 (5/14 오전)

PR #54 작업 중 황대원 PR 리뷰 코멘트 반영하면서 `nodes_graph/domain/ports/embedder_port.py` shim 방식 변경 시도. push 전에 박아름 PR #30 결정과 충돌 가능성을 짚으며 양해 요청. PR #54 현재 변경 파일 21개 중 embedder_port 관련은 미포함 (사전 협의만).

햄햄 제안 변경:
```python
# nodes_graph/domain/ports/embedder_port.py (변경 후 — shim)
from ai_agent.domain.ports.embedding_port import EmbedderPort
__all__ = ["EmbedderPort"]
```
정의는 `ai_agent/domain/ports/embedding_port.py`로 이동, nodes_graph는 re-export shim. 황대원 리뷰 근거: CLAUDE.md line 172 + REQ-004 spec line 95 모두 ai_agent 소유로 명시.

### 4.2 박아름 점검 결과

- 박아름 PR #30 (5/12 머지) 결정 = "nodes_graph SSOT, ai_agent.EmbeddingPort 폐기" — `modules/ai_agent/adapters/llm/modal_embedding_adapter.py:19-20` docstring에 명시 박힘
- SSOT 문서 충돌 상태 (REQ-003 spec / REQ-004 spec line 130~131은 nodes_graph, REQ-004 spec line 95/437 + CLAUDE.md line 172는 ai_agent stale)
- **이름이 다름** (`EmbedderPort` vs `EmbeddingPort`) — 원래 spec 의도는 두 port였을 수 있으나 5/12 박아름이 nodes_graph 한쪽으로 통합
- **의존성 방향 위반** — CLAUDE.md "modules 간 허용된 교차 import" 표에 `nodes_graph → ai_agent` 없음. shim도 위반에 해당
- 현재 import 사용처 10곳 모두 `from nodes_graph.domain.ports.embedder_port import EmbedderPort`

### 4.3 박아름 회수 권고 (PR #54 COMMENTED 게시)

https://github.com/billionaireahreum/Workflow_Automation/pull/54 (billionaireahreum, 2026-05-14 10:19 KST)

- shim 방식 회수 권고
- @dhwang0803 조장 멘션 → SSOT 결정 재합의 요청
  - 옵션 A (권장): CLAUDE.md / REQ-004 spec을 nodes_graph SSOT로 갱신 → embedder_port 변경 회수
  - 옵션 B: ai_agent로 옮기면 shim 아닌 완전 이전 + 사용처 10곳 일괄 갱신. 박아름 영역은 PR #51 후속 처리

### 4.4 햄햄 commit `466fd83` 7항목 반영 (5/14 10:28)

햄햄이 조장 리뷰 7항목 처리:
- 🔴 1 PgAgentMemoryRepository 시그니처: ✅ option (a) `async with session_factory() as session` + 주입 패턴
- 🟡 2 GCSMemoryStore embedding 누락: ✅ frontmatter 직렬화/역직렬화 추가
- 🟡 3 docs/scripts rot: ✅ `modal secret create` 직접 패턴으로 교체
- 🟡 **4 EmbeddingPort SSOT 위치: ⏸️ 보류** — "박아름님과 논의 후 별도 PR로 처리"
- 🟢 5 FastAPI Body(...): ✅ 적용
- 🟢 6 GCS 통합 테스트 teardown: ✅ autouse cleanup fixture
- 🟢 7 LoadUserMemoryUseCase created_at: ✅ metadata 분리

추가 개선: GCSMemoryStore GCS 블로킹 I/O 전체 `asyncio.to_thread()` 래핑.

### 4.5 박아름 추가 코멘트 (5/14 10:35)

https://github.com/billionaireahreum/Workflow_Automation/pull/54 (billionaireahreum)

- #1 option (a) 선택 정답 동의
- **#4 EmbeddingPort 보류 결정 +1** — 조장님도 "port를 ai_agent로 가져오는 게 의존성 역전이 되는 부분이 있다" 직접 언급. **nodes_graph SSOT 유지 그대로 진행**
- CLAUDE.md line 172 + REQ-004 spec line 95/437 stale 정정은 박아름이 PR #51 머지 후 후속 docs PR로 처리 약속
- #3 추가 개선 (`asyncio.to_thread()` 래핑) 칭찬

→ PR #54는 #4 보류로 머지 가능 상태 (조장 approve 대기). 박아름 영역 영향 0건.

---

## 5. SSOT 결정 3건 모두 확정 (5/14)

조장 + 박아름 + 신정혜 협의로 5/14 모두 결정.

| # | 결정 사안 | 결정 결과 | 처리 책임 |
|---|----------|----------|----------|
| 1 | health path: `GET /v1/health` vs `POST /v1/agent/health` | ✅ **SSOT 갱신** — 옵션 1 채택, GET /v1/health (REST 표준 + 코드 변경 0건). 신정혜 SSOT 갱신 PR에 포함 | 신정혜 |
| 2 | SSE 종결: dual vs single | ✅ **dual 통일** — 신정혜 패턴 채택 | 박아름 영역만 갱신 (신정혜 영역 이미 dual) + 신정혜 SSOT PR에 spec 명시 |
| 3 | embedder_port SSOT: nodes_graph vs ai_agent | ✅ **nodes_graph 유지** — PR #30 결정 + 의존성 방향 정합 | 박아름 후속 docs PR (PR #51 머지 후) — CLAUDE.md line 172 + REQ-004 spec line 95/437 stale 정정 |

### 5.1 신정혜 SSOT 갱신 PR 한 건에 들어갈 항목 (박아름 5/14 카톡 부탁)

1. REQ-004 spec line 250 — `POST /v1/agent/health` → `GET /v1/health` 정정
2. REQ-004 spec §4 응답 섹션 — SSE dual 종결 명시 한 줄 ("에러 종결 시 error frame + complete frame 순서로 발송. 정상 종결 시 complete frame만 발송.")
3. 다른 곳에 health path 언급 있으면 함께 정정

---

## 6. SSE dual 패턴 박아름 영역 적용 (저녁)

### 6.1 변경 범위

| 파일 | 변경 |
|---|---|
| `services/agents/agent-skills-builder/main.py` | +28 / -3 — `_done_frame_bytes` 헬퍼 추가 + `_stream` 4곳에 done frame 발송 (정상 / 예외 / unsupported source_type 모두) |
| `modules/ai_agent/tests/integration/test_agent_skills_builder.py` | +38 / -0 — `_done_frame_bytes` 검증 신규 3건 |

### 6.2 main.py 변경 핵심

**신규 헬퍼** (라인 91~107):

```python
def _done_frame_bytes() -> bytes:
    """SSE 스트림 종결 시그널 — frames=[], next_action='complete'.

    2026-05-14 결정: dual 종결 패턴 채택 (agent-composer/orchestrator와 통일).
    """
    from common_schemas.agent_protocol import AgentProtocolResponse

    return _sse_bytes(
        AgentProtocolResponse(
            frames=[],
            state_delta={},
            next_action="complete",
        )
    )
```

**`_stream` 종결 지점 3곳 추가**:
- unsupported source_type 분기 후 → done frame
- use case 정상 종료 (commit) 후 → done frame
- use case 내부 예외 catch 후 → ErrorFrame + done frame (raise 대신 명시 발송으로 contract 보장)

### 6.3 신규 테스트 3건

- `test_done_frame_bytes_emits_complete_terminator` — frames=[], state_delta={}, next_action="complete"
- `test_done_frame_bytes_follows_sse_data_line_format` — SSE "data: <json>\n\n" 포맷
- `test_done_frame_bytes_independent_of_business_payload` — 매 호출이 동일한 종료 시그널

`_stream`의 dual 종결 동작은 박아름 영역 정책(integration test가 modal/fastapi/asyncpg 의존성 없는 pure helper만 검증)을 따라 단위 테스트는 헬퍼 검증으로 한정. `_stream` 직접 검증은 PR #56 머지 후 e2e (Test plan #3)에서 처리.

### 6.4 테스트 결과

- skills_builder 한정: **134 → 137 통과**
- ai_agent 전체: **171 통과** (2.17s)

### 6.5 push 보류 상태

PR #51 후속 commit으로 push 예정이지만, PR #56 머지 후 Connector 패턴 적용 + bootstrap timeout 임시 패치 제거 작업과 묶어서 한 번에 push할지 단독 push할지 결정 보류.

---

## 7. 박아름 의존성 (5/14 마감 시점)

5/14 SSOT 결정 3건 모두 완료로 박아름 의존성이 단순화됨.

### 7.1 박아름 단독 진행 가능 (PR #56 머지 무관)

| 작업 | 소요 | 상태 |
|---|---|---|
| SSE dual 패턴 적용 (main.py + 테스트 3건) | 30분~1시간 | ✅ **5/14 완료** (commit/push 보류) |
| 5/14 진척 보고서 작성 (본 파일) | 30분 | ✅ **5/14 완료** |
| Test plan #2/#3 검증 시나리오 사전 정의 | 30분 | 잔여 |
| `agent-skills-builder` Modal app README 작성/갱신 | 30분~1시간 | 잔여 |
| PR #51 sanity check (137/137 재실행 + README/문서 누락 점검) | 30분 | 잔여 |
| embedder_port docs PR 사전 작성 (CLAUDE.md + REQ-004 spec stale 정정) | 30분~1시간 | 잔여, PR #51 머지 후 push |

### 7.2 PR #56 머지 후 진행 (대기)

| 작업 | 차단 해소 시 진입 |
|---|---|
| development pull (`git fetch origin` + `git merge origin/development`) | PR #56 머지 후 즉시 |
| Connector 패턴 적용 (commit `6390a43` 기준 lazy + loop 명시 바인딩) | development merge 후 즉시 |
| bootstrap_node_definitions.py 임시 timeout 180s 교체 코드 제거 | development merge 후 즉시 (정혜 commit `9d50311b`로 본질 해결) |
| modal deploy + /v1/health 200 검증 → Test plan #2 체크 | Connector 패턴 적용 후 즉시 |
| Orchestrator endpoint 통한 e2e 검증 → Test plan #3 체크 | health 통과 후 즉시 |
| 조장 PR #51 일괄 리뷰 요청 | #2 + #3 모두 통과 후 |

### 7.3 PR #51 머지 후 별도 docs PR

| 작업 | 트리거 |
|---|---|
| CLAUDE.md line 172 stale 정정 (`ai_agent/domain/ports/EmbeddingPort` → nodes_graph SSOT 명시) | PR #51 머지 후 |
| REQ-004 spec line 95, 437 stale 정정 | PR #51 머지 후 |

---

## 8. 박아름 결정 사항 (2026-05-14)

| 결정 | 사유 |
|------|------|
| PR #56 APPROVED + 권고 3건 동봉 | 3축 PASS이지만 박아름 영역 영향 cross-cutting 사안이라 즉시 명시 |
| PR #54 embedder_port shim 회수 권고 게시 (PR #54 본 작업 머지 OK) | 박아름 PR #30 결정 + 의존성 방향 정합 + 사용처 코드 변경 0건이 더 합리적 |
| SSE 종결 패턴 dual 통일 채택 | frontend "complete frame 받으면 종료" 단일 룰 + 박아름 영역 변경 비용(테스트 3건)이 신정혜 영역 변경 비용(코드 + redeploy)보다 작음 |
| SSE dual 적용 시 옵션 A (최소 변경) 채택 | 기존 `_classify_next_action` 유지 + 종결 지점 3곳에 done frame 추가만. 134 테스트 회귀 갱신 0건 |
| `_stream` dual 검증은 헬퍼 단위 테스트 + e2e로 분리 | integration test 정책(modal/fastapi/asyncpg 의존성 없는 pure helper만 검증) 준수. `_stream` 자체 검증은 PR #56 머지 후 Test plan #3에서 |
| embedder_port SSOT 갱신은 후속 docs PR로 분리 | PR #51 scope에 포함하면 리뷰 분산. 머지 후 단일 docs PR로 처리 |
| commit/push 보류 (작업 누적 후 한 번에 처리) | PR #56 머지 후 Connector 패턴 적용까지 묶어서 의미 있는 단위로 commit (5/14 박아름 흐름 결정) |

---

## 9. 참조

- spec: `docs/specs/REQ-004-ai-agent.md` §2.1, §3.1, §4
- plan: `docs/specs/plan/sprint-3.md`
- 가이드: `docs/guides/sub_agent_modal_deploy.md`
- 전일 보고서: `sprint-3-week1-2026-05-13-skills-builder.md`
- 박아름 메모리:
  - `project_sprint_3_day2_handoff.md` (Day 2~4 마감 + Day 5 진입점)
  - `feedback_branch_strategy.md`
  - `feedback_session_cleanup.md`
- PR #51: https://github.com/billionaireahreum/Workflow_Automation/pull/51
- PR #54: https://github.com/billionaireahreum/Workflow_Automation/pull/54
- PR #56: https://github.com/billionaireahreum/Workflow_Automation/pull/56
