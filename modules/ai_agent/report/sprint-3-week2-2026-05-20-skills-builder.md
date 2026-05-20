# Sprint 3 Week 2 — 박아름 agent-skills-builder FastAPI 정석 패턴 마이그레이션 Status (2026-05-20)

## 작업 요약

햄햄(이가원) PR #85 발견 본질 채택. `agent-skills-builder/main.py`가 사용하던 우회 패턴(`route(raw: dict[str, Any])` + 명시 `model_validate`)을 FastAPI 정석 `route(req: AgentProtocolRequest = Body(...))` 시그니처로 정정. 박아름 4 sub-agent 통일 흐름의 시작.

- **PR**: [#91 refactor(agent-skills-builder): FastAPI Body(...) 정석 패턴 — anti-pattern 제거](https://github.com/billionaireahreum/Workflow_Automation/pull/91)
- **branch**: `feature/req-004-skills-builder-fastapi-standard` → base=`development`
- **commit**: `36f3bd1`

## 본질

우회 패턴 도입 원인:
- `from __future__ import annotations` (PEP 563 deferred evaluation) → 모든 annotation을 string으로 lazy 평가
- + nested ForwardRef (`AgentProtocolRequest` → `AgentState`/`MemoryEntry`)
- FastAPI `get_type_hints()`가 string annotation resolve 실패
- → `PydanticUserError("not fully defined")` 발생

박아름 초기 처방: `model_rebuild()` 시도 → 안 됨 → 우회 패턴(`dict[str, Any]` + 명시 `model_validate`)으로 임시 해결. **anti-pattern** (FastAPI 자동 Body 검증/OpenAPI 자동 문서 손실).

햄햄이 PR #85에서 본질(`from __future__` 제거 시 FastAPI 정상 작동) 발견. 본 PR이 박아름 영역 마이그레이션.

## 변경 (1 파일 / +2 / -11)

| 줄 | 변경 |
|----|------|
| L50 `from __future__ import annotations` | **제거** |
| Import `from fastapi import ...` | `Body` 추가 |
| L292 `route(raw: dict[str, Any])` | `route(req: AgentProtocolRequest = Body(...))` |
| L300-304 우회 docstring | 제거 (본질 해소) |
| L306 `req = AgentProtocolRequest.model_validate(raw)` | 제거 (FastAPI 자동 검증) |

## 셀프 리뷰 (박아름 4축 룰)

| 축 | 결과 |
|----|------|
| 클린 아키텍처 의존성 위반 | ✅ 0건 (Composition Root 레이어 framework 사용 정합) |
| 타 모듈 import 문제 | ✅ 0건 (`Body` from fastapi 1개 추가만) |
| 스펙 정합 | ✅ 변경 0건 (spec은 endpoint URL/contract만, route 시그니처 internal) |
| SSOT | ✅ (common_schemas SSOT 그대로) |

## 검증

- [x] `pytest modules/ai_agent/tests/unit/application/skills_builder` — **117 passed (회귀 0)**
- [x] Modal 재배포 — `App deployed in 26.140s`
- [x] `GET /v1/health` — HTTP 200 `{"status":"ok","db":"iam-connected"}`
- [x] `POST /v1/agent/route` empty body — **HTTP 422 + FastAPI auto Body validation** (정석 패턴 작동, NameError 0)
- [x] CI gitleaks **pass** (재실행 후, 41s)

## 효과 (anti-pattern → 정석)

| 측면 | 우회 패턴 (이전) | 정석 패턴 (본 PR) |
|------|----------------|------------------|
| FastAPI 자동 Body 검증 | ❌ 명시 `model_validate` | ✅ 자동 |
| OpenAPI 자동 문서 (Swagger) | ❌ raw dict 시그니처 | ✅ Pydantic 스키마 자동 |
| 시그니처 가독성 | ⚠️ raw dict | ✅ Typed Pydantic 모델 |
| boilerplate | ⚠️ model_validate 호출 | ✅ 제거 |

## 연관 영역 (별도 PR 트랙)

| 영역 | 현재 패턴 | 진행자 / 상태 |
|------|----------|--------------|
| `agent-composer/main.py` | 정석 변경 완료 (5/20 9:39) | 신정혜 (별도 PR 예상) |
| `orchestrator/main.py` | 정석 변경 완료 (5/20 9:39) | 신정혜 (별도 PR 예상) |
| `agent-personalization/main.py` | PR #85 = 정석 | 햄햄 (PR #85 머지 시) |
| `llm-base/main.py` | 이미 `Body(...)` 정석 | 조장 (변경 X) |
| `common_schemas/agent_protocol.py` | `from __future__` + nested ForwardRef 유지 | 변경 0 (sub-agent 단독 변경으로 정합) |

→ 본 PR + 신정혜 별도 PR + 햄햄 PR #85 머지 시 **4 sub-agent 모두 정석 통일**.

## Impact Assessment

| 영역 | 영향 |
|------|------|
| `services/agents/agent-skills-builder/main.py` | 본 PR 범위 (1 파일 +2/-11) |
| `orchestrator` HTTPSubAgentClient 호출자 | 0 (endpoint URL/contract 동일) |
| 다른 sub-agent | 0 |
| `common_schemas` / spec / README / plan | 0 |
| 박아름 다른 영역 (auth/nodes_graph) | 0 |

머지 자체 영향 = 0 (external contract 동일).

## 박아름 4 sub-agent 통일 진행 흐름

```
5/20 09:00 햄햄 카톡 — sub-agent 4개 패턴 통일 제안 (PR #85 발견)
5/20 점심대 박아름 점검 — 우회 패턴 = anti-pattern 인정, 햄햄 본질 발견 확인
5/20 PR #91 박아름 정석 마이그레이션 + 셀프 리뷰 ← 본 보고서
5/20 09:39 신정혜 — composer + orchestrator 정석 교체 완료 (별도 PR 예상)
[대기] PR #85 머지 시 personalization 정석 통일
[대기] 신정혜 별도 PR 머지 시 4 sub-agent 모두 정석
```

## 관련 메모리

- [[project_fastapi_standard_pattern_2026_05_20]] — 본 작업 추적
- [[project_req002_jit_user_provisioning]] — PR #88 머지 완료 (5/19)
- [[project_skillsmp_compatibility_2026_05_19]] — SkillsMP 호환 (별도 트랙, 조장 8가지 답변 대기)
- [[feedback_modal_deploy]] — Modal 재배포 절차
