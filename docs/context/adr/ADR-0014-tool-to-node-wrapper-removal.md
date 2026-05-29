# ADR-0014: ToolToNodeWrapper 제거 + REQ-005 toolset 11종을 nodes_graph external/로 직접 등록

- **Status**: Accepted (호출 경로 A는 ADR-0018로 부분 대체)
- **Date**: 2026-05-15 (1차 햄햄·박아름 합의), 2026-05-19 (조장 안 반영 최종 확정 + 본 ADR 등록)
- **Deciders**: @billionaireahreum (박아름), @rooot0xyz (햄햄), @dhwang0803-glitch (조장)
- **Tags**: area/nodes_graph, area/toolset, area/execution_engine, layer/adapter, catalog

> **부분 대체 (Superseded in part by [ADR-0018](./ADR-0018-workflow-node-independent-execution-path.md), 2026-05-20)**
> Decision 항목 3(`process()`는 `NotImplementedError` + ToolsetExecutor 위임 메시지)과
> 항목 6(호출 경로 A — `workflow node → ToolsetExecutor → toolset.execute_tool()`)은
> ADR-0018로 폐기됐다. 워크플로우 노드는 `CatalogNodeExecutor`가 `BaseNode.process()`를
> 직접 호출하며(ADR-0018 Phase 3d 기준 53종 전부 실구현), `ToolsetExecutor` 경로는 제거됐다.
> 본 ADR의 핵심 결정인 "Tool = AI 내부 / Node = workflow 구성요소" SSOT 원칙은 그대로 유효하다.

## Context

REQ-003 spec 초안(5/14 작성) 작성 시점에 REQ-005 toolset 모듈의 14종 도구를 워크플로우 카탈로그에 노출하기 위해 두 가지 어댑터를 임시 도입했다.

- **`modules/nodes_graph/adapters/catalog/tools/toolset_nodes.py`** — 14종 `NodeDefinition`을 명시 정의
- **`modules/nodes_graph/adapters/tool_to_node_wrapper.py`** — `BaseTool` → `NodeDefinition` 변환 어댑터(`ToolToNodeWrapper`)

박아름이 1주차에 햄햄 toolset 모듈이 만들어지기 전(`modules/toolset/adapters/tools/*_tool.py` 14 파일 부재 상태)에 카탈로그가 비지 않도록 임시 배치한 것이다.

5/18 PR #71(햄햄 PHASE 1)이 머지되어 toolset 14 도구가 실제 구현체로 채워지자, 임시 `toolset_nodes.py`와 `tool_to_node_wrapper.py`가 **중복**이 되어 정리가 필요해졌다.

### 두 차례의 합의 흐름

| 시점 | 결정 | 분류 |
|------|------|------|
| **5/15 1차 (햄햄·박아름)** | 14종을 3분류: Node 유지 6 + Internal Tool 5 + 중복 제거 3 | Internal Tool 5(`file_*`/`json_transform`/`data_mapping`)는 toolset 모듈 내부에만 유지, nodes_graph 카탈로그에서 제외 |
| **5/18 박아름 호출 경로 점검 발견** | `services/execution_engine/src/adapters/toolset_executor.py:35` `tool_name = config.node_type` — 카탈로그 미등록 시 `ToolsetExecutor` 호출 경로 부재. AI Agent LLM tool wiring도 현재 코드 0건 | 5/15 합의의 Internal Tool 5종이 **데드 코드** 위험 |
| **5/19 조장 안 (최종 확정)** | "11종 모두 external/로 무조건" — 5/15 Internal Tool 5종도 카탈로그 등록. 중복 3종(`http_request_tool`/`conditional`/`loop`)만 양쪽 제거 | 박아름 객관 점검 5축 PASS + 햄햄 재합의 완료 |

## Decision

1. **`modules/nodes_graph/adapters/tool_to_node_wrapper.py` 삭제** — 사용처 0건, `ToolToNodeWrapper` 변환 어댑터 자체를 폐기.
2. **`modules/nodes_graph/adapters/catalog/tools/toolset_nodes.py` + 디렉토리 삭제** — 임시 명시 NodeDefinition 14종 일괄 제거.
3. **`modules/nodes_graph/adapters/catalog/external/`에 11종 NodeDefinition 개별 파일로 신규 등록**:
   - `rest_api`, `graphql`, `webhook`, `email_send`, `slack_notify`, `text_template`, `json_transform`, `data_mapping`, `file_read`, `file_write`, `file_transform`
   - `BaseNode` 상속 + `dataclass Input/Output` + `process()`는 `NotImplementedError` + ToolsetExecutor 위임 메시지 (`anthropic_chat` 패턴 정합).
4. **중복 3종 양쪽 제거**:
   - `http_request_tool` — `external/http_request`와 의미 동일
   - `conditional` — `domain/control/if_condition`과 의미 동일
   - `loop` — `domain/control/loop_list`와 의미 동일
   - toolset 모듈에서도 동시 제거 (햄햄 후속 PR).
5. **카탈로그 종 수**: 56 → **53** (28 domain + 25 external + 0 toolset_nodes). SkillNode 30 포함 시 86 → **83**.
6. **호출 경로 두 갈래 명시**:
   - 경로 A: `workflow node → execution_engine.ToolsetExecutor (node_type 기반) → toolset.execute_tool()` (사용자 그래프)
   - 경로 B (조장 5/19 LLMPort 설계 안 후속): `LLM tool call → tool_use_loop → toolset_dispatcher → toolset.execute_tool()` (AI 자동)
   - 11종은 양쪽 경로에서 호출 가능. ADR-0014의 본 PR(#78)이 경로 A를 완성. 경로 B는 별도 ADR(조장 신규 안)로 분리.

### "Tool = AI 내부 / Node = workflow 구성요소" 원칙 SSOT 격상

5/15 햄햄·박아름 합의 시점 보고서(`modules/ai_agent/report/sprint-3-week1-2026-05-15-skills-builder.md` §3.1)에만 머물러 있던 책임 분리 원칙을 본 ADR로 공식 SSOT 격상한다.

- **Tool** (`modules/toolset/adapters/tools/<name>_tool.py`) = AI Agent가 내부적으로 호출하는 도구. `BaseTool` 인터페이스.
- **Node** (`modules/nodes_graph/adapters/catalog/external/<name>.py` 또는 `domain/catalog/*`) = 사용자가 워크플로우 그래프에 끌어다 쓰는 노드. `BaseNode` 인터페이스.
- 11종(2026-05-19 기준)은 동일 `node_type`이 양쪽에 존재 — 같은 도구를 Node와 Tool로 둘 다 노출.

## Consequences

### 긍정

- 워크플로우에서 11종을 즉시 노드로 호출 가능 (사용자 표현력 보존).
- 카탈로그 등록 일관성 — 모든 외부 호출 노드가 `adapters/catalog/external/`에 단일 위치.
- `BaseNode.process()` NotImplementedError 패턴이 `anthropic_chat`/`gemma_chat`과 정합.
- `ToolToNodeWrapper` 동적 변환 코드 제거로 IDE/타입 추론 개선.
- 박아름 호출 경로 부재 발견 (5/18) 자동 해결.

### 부정 / 제약

- toolset 모듈 측 도구(11종)와 nodes_graph 측 NodeDefinition(11종)이 분리되어 **두 곳을 동시에 유지**해야 한다. 한쪽 시그니처 변경 시 다른 쪽 정합 검증 필요. (수동 정합 — 추후 codegen 검토 가능)
- `file_read`/`file_write`/`file_transform`/`email_send`/`webhook` 등 RiskLevel.HIGH 도구가 카탈로그에 노출되어 사용자가 임의 그래프 구성 가능. **권한 게이팅(보안 정책) 필수** — 햄햄 PHASE 2에서 toolset 도구 자체 입력 검증(allowlist / sandbox)으로 처리.
- 중복 3종 제거로 인해 DB `node_definitions` row 정리 필요 (86 → 83). [[feedback_db_safety]] 카톡 협의 후 별도 사이클.

### 외부 모듈 영향

- **execution_engine** — `ToolsetExecutor`(`toolset_executor.py:35`) 그대로 동작. node_type 변경 없음.
- **toolset** — 모듈 자체 변경 X. 햄햄이 후속 PR로 중복 3종(`http_request_tool`/`conditional`/`loop`) 도구 제거.
- **ai_agent / auth / storage** — 영향 0. NodeDefinition 필드 변경 없음.

## Alternatives Considered

### (A) 5/15 분류 그대로 (Internal Tool 5종 toolset에만)
- ❌ `ToolsetExecutor` 호출 경로 부재 → 데드 코드
- LLM tool wiring 추가 작업 필요 (현재 ai_agent 코드 0건)

### (B) `ToolToNodeWrapper` 유지 + 동적 등록
- ❌ 임시 어댑터를 영구화. 명시 import(옵션 A) 결정과 충돌(`plan/sprint-3-catalog-plugin-discovery.md` §3).
- IDE 타입 추론 약화.

### (C) toolset 14종 모두 카탈로그에서 제거 (사용자 노출 0)
- ❌ 워크플로우에서 외부 API/Slack 등 핵심 도구 호출 불가. 사용자 표현력 손실.

## Related ADRs

- ADR-0001 (모노레포 구조) — toolset/nodes_graph 모듈 분리의 전제.
- ADR-0013 (EmbedderPort SSOT) — Port 소유 모듈과 구현체 소유 모듈 분리 패턴(예외 케이스)의 선례. 본 ADR은 일반 패턴(Tool/Node 양쪽 등록) 정의.
- ADR-XXXX (조장 5/19 LLMPort tools 파라미터 + tool_use_loop 안) — 미작성. 호출 경로 B 정식화 시 추가 예정.

## References

- PR #78: https://github.com/billionaireahreum/Workflow_Automation/pull/78
- 5/15 합의 보고서: `modules/ai_agent/report/sprint-3-week1-2026-05-15-skills-builder.md` §3.1~3.6
- 5/18 호출 경로 부재 발견: `modules/ai_agent/report/sprint-3-week2-2026-05-18-park-areum-status.md` (로컬 전용) + memory `project_toolset_cleanup_blocker_2026_05_18.md`
- 5/19 박아름 작업 보고서: `modules/nodes_graph/report/sprint-3-week2-2026-05-19-park-areum-status.md`
- REQ-003 spec L451~497 (카탈로그 표 53종 갱신)
- REQ-005 spec L143~178 (toolset 14종 정의, DelayTool 제외 사유)
