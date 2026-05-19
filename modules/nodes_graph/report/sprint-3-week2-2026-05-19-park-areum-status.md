# 박아름 nodes_graph 영역 작업 현황 (2026-05-19 화)

**작성자**: 박아름
**기준 브랜치**: `feature/req-003-nodes-graph`
**담당 영역**: REQ-003 nodes_graph (toolset 정리 PR #78)
**마지막 갱신**: 2026-05-19 (화) — **PR #78 생성 완료** (3 commits, origin push)

---

## 한 줄 요약

**toolset 14종 → external/ 11종 분리 + 중복 3종 양쪽 제거 + ToolToNodeWrapper 제거**. 카탈로그 56 → 53종 (28 domain + 25 external). 5/15 햄햄·박아름 합의 + 5/19 조장 안(11종 external 이전 무조건) 반영. **PR #78 머지 대기**.

---

## 1. 5/19 작업 흐름

### 1.1 진입 트리거 — 5/18 PR #71(햄햄 PHASE 1) 머지 후

| 시점 | 이벤트 | 행동 |
|------|--------|------|
| 5/18 저녁 | PR #71 머지 (toolset 모듈 ToolCategory Enum + 14종 도구 PHASE 1) | development sync (53 ff) + REQ-003 메인 ff |
| 5/18 저녁 | 박아름이 호출 경로 정밀 점검 시작 | `services/execution_engine/src/adapters/toolset_executor.py:35` 확인 |
| 5/18 저녁 | **호출 경로 부재 발견** (5종 Internal Tool 카탈로그 제거 시 데드 코드) | 햄햄 카톡 발송 → "5/15 합의 그대로 진행" 답변 |
| 5/19 오전 | 조장 의견 도착 — **"11종 모두 external/로 무조건"** | 박아름 객관 점검 5축 → 조장 안 동의 |
| 5/19 오후 | 햄햄 재합의 — "기술적으로 맞음. file_* 보안 PHASE 2 햄햄 처리 OK" | 작업 진입 |

### 1.2 5/15 합의 vs 5/19 조장 안 차이

| 분류 | 5/15 합의 | 5/19 조장 안 (채택) |
|------|-----------|-------------------|
| Node 유지 6종 (rest_api/graphql/webhook/email_send/slack_notify/text_template) | external/ 이전 | external/ 이전 (동일) |
| Internal Tool 5종 (json_transform/data_mapping/file_*) | **toolset에만** | **external/도 이전** ← 변경 |
| 중복 제거 3종 (http_request_tool/conditional/loop) | 양쪽 제거 | 양쪽 제거 (동일) |

### 1.3 조장 안 채택 객관 근거 (5축)

1. **호출 경로** — ToolsetExecutor가 node_type 기반이라 카탈로그 등록 필수. 5종 빼면 데드 코드
2. **워크플로우 표현력** — 파일 처리/JSON 변환 시나리오 살아남
3. **REQ-003 spec 원본 의도** — L489-494가 11종 모두 카탈로그 등록 가정
4. **햄햄 우려 두 개 해소** — 보안은 도구 자체 검증 / AI 내부 처리는 LLM tool wiring으로 (둘 다 카탈로그 위치와 독립)
5. **햄햄 5/15 후반 흔들림 흔적** — 햄햄도 11종 external 일원화 시도했었음

---

## 2. PR #78 변경 사항

### 2.1 코드 (Commit `304aa62`)

| 영역 | 변경 |
|------|------|
| `adapters/catalog/external/` | **11 파일 신규** (BaseNode + dataclass Input/Output + process() NotImplementedError + ToolsetExecutor 위임 메시지) |
| `adapters/catalog/tools/` | **디렉토리 제거** (toolset_nodes.py + __init__.py) |
| `adapters/tool_to_node_wrapper.py` | **제거** (사용처 0건) |
| `adapters/__init__.py` | ToolToNodeWrapper re-export 제거 |
| `application/catalog_registry.py` | toolset_nodes import 제거 + external 11 추가 |
| `adapters/catalog/registry.py` | docstring 46 → 53 |
| `database/seeds/node_definitions.json` | 56 → 53 entry |
| `tests/unit/adapters/test_registry.py` + `tests/unit/domain/test_catalog.py` | 종 수 53 갱신 |

### 2.2 spec + README + docstring (Commit `b7fa145`)

| 파일 | 변경 |
|------|------|
| `docs/specs/REQ-003-nodes-graph.md` | 카탈로그 표 56 → 53, ToolToNodeWrapper 섹션 제거, 56 인용 일괄 정정 |
| `modules/nodes_graph/README.md` | adapters 표 + 의존 관계 갱신, 54 → 53 |
| `modules/nodes_graph/pyproject.toml` | description 54 → 53 |
| domain entity/port docstring 4 | `base_node.py` / `node_definition.py` / `embedder_port.py` / `node_definition_repository.py` 54 → 53 |

### 2.3 plan 추가 정정 (Commit `80257c9`)

5/19 self-review 3축 점검 중 발견. PR 보강:
- `plan/sprint-3-catalog-plugin-discovery.md` L102/113 (ToolToNodeWrapper 경유 → ToolsetExecutor 위임)
- `plan/REQ-003-nodes-graph-plan.md` L37/116/139 (Adapter Layer 표 갱신, 미결 사항 갱신)

---

## 3. 카탈로그 종 수 변화

| 시점 | 구성 | 합계 (with SkillNode 30) |
|------|------|--------------------------|
| 5/18 PR #71 머지 후 | 28 domain + 14 external + 14 toolset_nodes | 56 (86) |
| **PR #78 머지 후** | 28 domain + **25** external + 0 toolset_nodes | **53** (**83**) |

### 카테고리 분포 (REQ-003 spec L489 정합)

```
trigger    6
condition  8  (이전 10에서 -2, conditional/loop 제거)
transform  18 (이전 14에서 +4, file_transform/json_transform/text_template/data_mapping)
ai         2
integration 10 (이전 11에서 -1, http_request_tool 제거 / rest_api/graphql 추가 = 8+2)
output     2
action     5  (이전 2에서 +3, webhook/email_send/slack_notify)
utility    2  (이전 0에서 +2, file_read/file_write)
────────────
합계        53 ✓
```

JSON 카운트 정합 (Python `Counter` 검증):
- transform 18 / condition 8 / trigger 6 / ai 2 / integration 10 / output 2 / action 5 / utility 2 → **53 ✓**

---

## 4. Self-review 3축 결과

| 축 | 결과 | 검증 |
|----|------|------|
| **SSOT** (스펙 정합) | ✅ PASS | REQ-003 spec 카탈로그 표 = JSON 53 카테고리 분포 100% 일치 |
| **타 모듈 의존성** | ✅ PASS | 신규 11 파일 import 전수 — toolset/ai_agent/storage/langgraph/fastapi/celery/sqlalchemy 0건. 외부에서 deleted 파일 import 0건 |
| **클린 아키텍처** | ✅ PASS | adapters/catalog/external/ → domain/entities 단방향. domain 프레임워크 import 0건 |

### 회귀 테스트 — 116 passed

```
pytest modules/nodes_graph/tests/
============================= 116 passed in 0.96s =============================
```

---

## 5. 호출 경로 (5/19 조장 안 + 박아름 PR #78 후 그림)

신규 11종은 **두 경로**로 호출 가능:

### 경로 A — Workflow Node (사용자 그래프)
```
사용자가 React Flow에 끌어다 놓음
  → workflow.nodes[].type = "rest_api"
  → execution_engine.ToolsetExecutor
  → tool_name = config.node_type     [toolset_executor.py:35]
  → toolset.execute_tool(...)
  → toolset/adapters/tools/rest_api_tool.py 실행
```

### 경로 B — LLM Tool (AI 자동, 조장 신규 안 PR — 박아름 영역 아님)
```
LLM이 tools 파라미터로 호출 결정
  → tool_use_loop (ai_agent/application/)
  → toolset_dispatcher (ai_agent/adapters/tools/)
  → toolset.execute_tool(...)
  → toolset/adapters/tools/rest_api_tool.py 실행
```

→ 양립. 박아름 PR #78이 경로 A를 처리. 경로 B는 조장 안 후속 PR (신정혜/햄햄/조장 영역).

---

## 6. 별도 사이클 — 박아름 PR 머지 후

### 6.1 DB row sync (86 → 83) — 카톡 협의 필수

[[feedback_db_safety]] 룰: 공유 DB 수정 전 카톡 협의 + 사전 영향 평가.

- 삭제 대상: `http_request_tool`, `conditional`, `loop` 3 row
- 협의 대상: 조장(테이블 owner) + 햄햄(toolset 도구 owner) + 신정혜(SkillNode 참조)
- 영향 평가: 다른 사람이 만든 워크플로우/SkillNode가 3 node_type 참조 중인지

### 6.2 조장 영역 stale 10곳 — 별도 정정 요청

특히 `scripts/verify_schema_v2.py:138` `"node_definitions = 54"` 하드코딩 — **우선순위 1** (본 PR 머지 후 DB row 53 동기화 시 검증 FAIL).

| 파일 | 라인 |
|------|------|
| `MONOREPO_STRUCTURE.md` | L87, L215 |
| `docs/TEAM_GUIDE.md` | L10 |
| `docs/context/adr/ADR-0002` | L40, L63 |
| `docs/context/clean_architecture.md` | L326, L1265 |
| `_agent_templates/TEST_WRITER.md` | L166 |
| `scripts/apply_seeds.py` | L1, L26 |
| `scripts/apply_seeds_v2.py` | L32 |
| `scripts/verify_schema_v2.py` | L138 ⚠️ |
| `scripts/verify_pr8.py` | L55 |
| `scripts/bootstrap_node_definitions.py` | L329 |
| `database/scripts/seed.py` | L1 |

### 6.3 햄햄 영역 stale 3곳 — 햄햄 알림

- `modules/toolset/README.md` L132 (`ToolToNodeWrapper로 BaseTool → NodeDefinition`)
- `docs/specs/plan/req-005-overview.md` L28, L210 (`ToolToNodeWrapper` 인용)

### 6.4 조장 5/19 LLMPort 설계 안 — ADR 대기

조장이 "LLMPort.generate() tools 파라미터 + tool_use_loop + toolset_dispatcher" 설계 안 공유. ADR 초안 작성 예정. 박아름 영역 코드 변경 0건, ADR 도착 시 박아름 리뷰만.

---

## 7. 다음 트리거

| 트리거 | 박아름 행동 |
|--------|-----------|
| **PR #78 조장 리뷰 + 머지** | 카톡 알림 발송 (조장 + 햄햄) + DB cleanup 카톡 협의 진입 |
| **조장 ADR 초안 도착** | ADR 리뷰 (호출 경로 두 갈래 / 11종 양쪽 wiring / RiskLevel 게이팅 필수 짚어주기) |
| **조장 영역 stale 10곳 정정 PR** | `verify_schema_v2.py:138` 우선순위 1 확인 |

---

## 8. 관련 문서

- PR #78: https://github.com/billionaireahreum/Workflow_Automation/pull/78
- ADR-0014: `docs/context/adr/ADR-0014-tool-to-node-wrapper-removal.md` (본 PR 결정 기록)
- REQ-003 spec: `docs/specs/REQ-003-nodes-graph.md` (53종 갱신)
- 5/15 햄햄 합의 사실관계: `modules/ai_agent/report/sprint-3-week1-2026-05-15-skills-builder.md` §3
