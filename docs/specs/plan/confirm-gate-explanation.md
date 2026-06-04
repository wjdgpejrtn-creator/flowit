# 실행 계획: 신뢰 가능한 컨펌 게이트 (워크플로우 설명 + 권한 매니페스트)

> 작성 2026-05-31 · 대상 모듈: `common_schemas`(REQ-012) · `ai_agent`(REQ-004) · `frontend`(REQ-010)
> 이 문서 하나로 구현 가능하도록 파일·삽입 지점·수용 기준을 못박았다. 순서대로 진행.

---

## 1. 배경 & 목표

우리 에이전트는 **one-shot(HITL 없음)** 철학이다. 워크플로우 초안을 한 번에 만들어 보여주고 사용자에게 최종 컨펌(▶ 실행)만 받는다. HITL을 없앤 대가로 **신뢰를 벌 기회가 컨펌 게이트 한 곳에 전부 몰린다.**

현재 컨펌 게이트는 너무 얇다:

```
ResultFrame(status="ready_to_execute", message="워크플로우가 완성됐습니다. 실행 버튼을 클릭해 실행하세요.")
```

→ 사용자는 블랙박스를 그냥 믿고 실행해야 한다. 불안 → 이탈.

**목표:** 컨펌 게이트가 "이 워크플로우가 **무엇을** 하고, **무엇을 건드리며**, **무엇을 가정했는지**"를 보여주게 만든다. HITL을 추가하지 않고(철학 유지) 신뢰를 확보한다.

### 신뢰 게이트 5요소

| # | 요소 | 출처 | 비고 |
|---|------|------|------|
| 1 | 의도 재진술 | `state["messages"]` 첫 user 메시지 / `draft_spec` | 오해 즉시 포착 |
| 2 | 단계별 평문 설명 | 그래프 노드 순서 + `NodeConfig.description` | "①트리거 →②시트 읽기 →③요약 →④Slack" |
| 3 | **권한/사이드이펙트 매니페스트** | `NodeConfig.required_connections` + `risk_level` | **가장 큰 신뢰 레버** |
| 4 | 가정·기본값 선언 | `NodeInstance.parameters` vs `input_schema` default | HITL의 대체재 |
| 5 | 원클릭 교정 | 기존 edit mode(`FlowEditor`) | 예방 대신 값싼 사후 교정 |

---

## 2. 설계 원칙 (반드시 준수)

1. **설명은 schema에서 derive한다. LLM 자유 서술 금지.**
   단계/권한/가정은 `WorkflowSchema` + `NodeConfig`에서 **결정론적으로 추출**한다. LLM은 추출된 사실을 **읽기 좋게 다듬는 용도로만**(summary 문장) 쓴다. 그래프와 어긋난 설명문은 신뢰를 *파괴*한다 — 실행 결과가 설명과 다르면 최악.
2. **LLM은 선택적.** `LLMPort`가 주입 안 되면 템플릿 fallback. (`_general_chat_node`의 `if self._llm is None` 패턴 그대로)
3. **기존 자산 재사용.** 새 프레임 타입 만들지 않는다 — `ResultFrame.payload`를 확장하고 기존 `ChatMessageFrame`을 쓴다. 프론트 컨펌 카드(`readyToExecute`)를 확장한다.
4. **Clean Architecture 준수.** 추출 로직은 `ai_agent/domain/services/`의 순수 도메인 서비스. 프레임워크 import 금지.
5. **공유 타입은 `common_schemas`에 단일 정의** → pydantic2ts로 프론트 타입 자동 생성.

---

## 3. 데이터 모델 (신규)

`common_schemas`에 `WorkflowExplanation` VO를 추가한다. ResultFrame.payload에 직렬화되어 실리고, 프론트는 codegen된 동일 타입을 쓴다.

```python
# packages/common_schemas/python/common_schemas/workflow_explanation.py  (신규)
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .enums import RiskLevel


class ExplanationStep(BaseModel):
    model_config = ConfigDict(frozen=True)
    order: int                       # 1-based 실행 순서
    node_name: str                   # NodeConfig.name
    description: str                 # NodeConfig.description (또는 LLM 다듬은 한 줄)
    risk_level: RiskLevel


class PermissionItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    connection: str                  # required_connections 원소 (예: "slack", "google_sheets")
    node_name: str                   # 이 권한을 요구하는 노드
    risk_level: RiskLevel            # 해당 노드 risk → 쓰기/위험 강조용


class WorkflowExplanation(BaseModel):
    model_config = ConfigDict(frozen=True)
    intent_restatement: str          # ① 의도 재진술
    summary: str                     # 평문 한 단락 (LLM 다듬음 or 템플릿)
    steps: list[ExplanationStep] = Field(default_factory=list)        # ②
    permissions: list[PermissionItem] = Field(default_factory=list)  # ③ (connection 기준 dedup)
    assumptions: list[str] = Field(default_factory=list)             # ④
```

---

## 4. 파일 단위 작업

### 영역 A — `common_schemas` (REQ-012, 황대원)

> `common_schemas_update_checklist` 7단계 그대로 따른다.

| # | 파일 | 작업 |
|---|------|------|
| A-1 | `packages/common_schemas/python/common_schemas/workflow_explanation.py` | **신규.** §3 모델 3개 정의 |
| A-2 | `packages/common_schemas/python/common_schemas/__init__.py` | `WorkflowExplanation`, `ExplanationStep`, `PermissionItem` export 추가 |
| A-3 | `packages/common_schemas/python/tests/test_init.py` | 위 3개 import 가능 테스트 추가 |
| A-4 | `packages/common_schemas/python/tests/test_workflow_explanation.py` | **신규.** 직렬화/frozen/기본값 단위 테스트 |
| A-5 | `packages/common_schemas/typescript/src/generated/index.ts` | pydantic2ts 재생성 (수기 편집 금지, 코드젠 명령 실행) |
| A-6 | `packages/common_schemas/CHANGELOG.md` + `pyproject.toml` | 마이너 버전 bump + 변경 기록 |

**수용 기준:** `from common_schemas import WorkflowExplanation` 동작 + 프론트 `@common/generated`에 `WorkflowExplanation` 타입 존재.

---

### 영역 B — `ai_agent` 도메인 서비스 (REQ-004, 신정혜)

추출 로직은 순수 도메인 서비스. mock 없이 테스트 가능해야 한다.

| # | 파일 | 작업 |
|---|------|------|
| B-1 | `modules/ai_agent/domain/services/workflow_explanation_service.py` | **신규.** 아래 시그니처 |
| B-2 | `modules/ai_agent/tests/unit/domain/test_workflow_explanation_service.py` | **신규.** 결정론 추출 검증 (LLM 없이) |

```python
# B-1 시그니처
class WorkflowExplanationService:
    def build(
        self,
        workflow: WorkflowSchema,
        node_configs: dict[UUID, NodeConfig],   # node_id → NodeConfig
        user_intent: str,                        # 첫 user 메시지 / draft_spec.natural_language_intent
    ) -> WorkflowExplanation:
        ...
```

**구현 규칙:**
- **steps**: `workflow.connections`(Edge)로 위상 순서를 만들고, 각 `NodeInstance.node_id`를 `node_configs`에서 찾아 `name`/`description`/`risk_level`로 `ExplanationStep` 생성. 엣지가 선형이 아니면 `nodes` 순서 fallback.
- **permissions**: 각 노드의 `NodeConfig.required_connections`를 펼쳐 `PermissionItem` 생성. **connection 기준 dedup**, `risk_level` 높은 노드 우선 표기.
- **assumptions** (v1, 가벼운 버전): `NodeInstance.parameters` 중 값이 `NodeConfig.input_schema`의 `default`와 동일한 항목을 "기본값 가정"으로 표기. 예: `"전송 시각: 09:00 (기본값)"`. 트리거/스케줄 파라미터 우선.
- **summary / intent_restatement**: 이 서비스는 **사실만 채운다**. summary는 단계+권한을 조합한 템플릿 문장으로 1차 생성(LLM 다듬기는 영역 C에서). `intent_restatement`는 `user_intent` 그대로.
- **프레임워크 import 절대 금지** (FastAPI/LangGraph/SQLAlchemy). `common_schemas`와 자기 도메인만.

**수용 기준:** WorkflowSchema + NodeConfig dict만 주면 LLM 없이 `WorkflowExplanation`이 결정론적으로 나온다. 같은 입력 → 같은 출력.

---

### 영역 C — composer 그래프 wiring (REQ-004, 신정혜)

| # | 파일 | 작업 |
|---|------|------|
| C-1 | `modules/ai_agent/adapters/langgraph/composer_graph.py` | `_State`에 필드 추가 + `_explain_node` 신규 + 그래프 재배선 + confirm payload 확장 |
| C-2 | `modules/ai_agent/tests/unit/application/workflow_composer/test_compose_workflow.py` | 최종 ResultFrame payload에 `explanation` 존재 검증 |

**C-1 세부:**

**(a) `_State` TypedDict (line 120 부근)에 추가:**
```python
explanation: WorkflowExplanation | None
```
초기화부(line 239 `"saved_workflow_id": None,` 부근)에 `"explanation": None,` 추가.

**(b) 신규 노드 `_explain_node`** — `save_workflow`(handoff) 직후, `confirm_result` 직전에 삽입:
```python
async def _explain_node(self, state: _State) -> dict:
    workflow = state.get("workflow_draft")
    if workflow is None:
        return {}

    # node_id → NodeConfig 해석. state["node_candidates"] 재사용 + 누락분만 get_schema
    cfg_lookup = {c.node_id: c for c in (state.get("node_candidates") or [])}
    for inst in workflow.nodes:
        if inst.node_id not in cfg_lookup:
            try:
                cfg_lookup[inst.node_id] = await self._node_registry.get_schema(inst.node_id)
            except Exception:
                continue

    user_intent = ""
    if state.get("draft_spec"):
        user_intent = state["draft_spec"].natural_language_intent
    elif state["messages"]:
        user_intent = state["messages"][0].get("content", "")

    explanation = WorkflowExplanationService().build(workflow, cfg_lookup, user_intent)

    # LLM 다듬기 (선택적, 사실 기반 grounding)
    if self._llm is not None:
        try:
            facts = explanation.model_dump_json()
            prompt = (
                "다음 JSON은 워크플로우의 검증된 사실이다. 이 사실만 사용해 "
                "사용자에게 보여줄 2~3문장 한국어 요약을 써라. 사실에 없는 내용 추가 금지.\n"
                f"{facts}"
            )
            polished = await self._llm.generate(prompt)
            explanation = explanation.model_copy(update={"summary": polished.strip()})
        except Exception as exc:
            _logger.warning("explain LLM 다듬기 실패 (템플릿 유지): %s", exc)

    return {
        "explanation": explanation,
        "collected_frames": [
            ChatMessageFrame(role="assistant", content=explanation.summary),
            PipelineStatusFrame(service_name="explain", status="completed"),
        ],
    }
```

**(c) 그래프 재배선** (line 1152~1192 영역):
```python
graph.add_node("explain", self._explain_node)          # 신규
# 기존:  graph.add_edge("save_workflow", "confirm_result")
graph.add_edge("save_workflow", "explain")             # 변경
graph.add_edge("explain", "confirm_result")            # 신규
```
나머지 엣지(`confirm_result → save_memory → END`)는 그대로.

**(d) `_user_confirm_node` (line 1040) payload 확장:**
```python
explanation = state.get("explanation")
payload = {
    "workflow_id": str(workflow_id) if workflow_id else None,
    "status": "ready_to_execute",
    "message": "워크플로우가 완성됐습니다. 아래 설명을 확인하고 실행하세요.",
    "session_id": str(state["session_id"]),
}
if explanation is not None:
    payload["explanation"] = explanation.model_dump(mode="json")
# ResultFrame(intent="propose", payload=payload) ...
```

**(e) 일관성 — `_execute_node` 비실행 분기 (line 894~907):** 동일하게 `explanation`을 payload에 실어 두 emit 경로의 계약을 맞춘다. (state에 explanation이 있으면 첨부)

**수용 기준:** 정상 초안 생성 e2e에서 마지막 `result` 프레임 payload에 `explanation` 객체(intent_restatement/summary/steps/permissions/assumptions)가 포함된다.

> ⚠️ **Ownership 통지:** `ai_agent`(composer)는 신정혜님 소유 모듈. 영역 B·C는 신정혜님이 구현하거나, 타인 구현 시 PR body에 사후 통지 + 사전 협의. (cross_owner_module_etiquette)

---

### 영역 D — 프론트엔드 컨펌 카드 (REQ-010, 황대원)

| # | 파일 | 작업 |
|---|------|------|
| D-1 | `services/frontend/src/stores/agentStore.ts` | `readyToExecute`에 `explanation?: WorkflowExplanation` 필드 추가 |
| D-2 | `services/frontend/src/components/agent/ConfirmCard.tsx` | **신규.** 5요소 렌더링 컴포넌트 |
| D-3 | `services/frontend/src/app/agent/page.tsx` | `result` 프레임 핸들러가 `payload.explanation` 파싱 + 컨펌 카드를 `ConfirmCard`로 교체 |
| D-4 | `services/frontend/src/app/agent/__tests__/AgentPage.test.tsx` | explanation 포함 result 프레임 → 카드 렌더 검증 |

**D-1:** `setReadyToExecute` 인자 타입에 `explanation?: WorkflowExplanation` 추가 (`@common/generated`에서 import).

**D-3:** `page.tsx` line 515~528 `case 'result'` 블록에서:
```typescript
if (payload?.status === 'ready_to_execute') {
  setReadyToExecute({
    workflowId: payload.workflow_id as string,
    message: (payload.message as string) ?? '워크플로우가 완성됐습니다.',
    explanation: payload.explanation as WorkflowExplanation | undefined,  // 추가
  });
}
```
그리고 line 706~718의 `readyToExecute` 렌더 블록을 `<ConfirmCard explanation={readyToExecute.explanation} onExecute={handleExecute} loading={executeLoading} />`로 교체.

**D-2 `ConfirmCard` 렌더 사양:**
- **의도 재진술**: "요청하신 내용: {intent_restatement}"
- **요약 단락**: {summary}
- **단계 리스트**: steps를 번호와 함께 (`①②③`), 각 줄 끝에 risk_level 칩(`RiskPill` 재사용)
- **권한 매니페스트** (강조 박스): "이 워크플로우가 접근하는 것:" + permissions를 `connection` + risk 강조로 나열. **high/medium risk는 시각적으로 강조** (빨강/주황)
- **가정** (접을 수 있는 섹션): assumptions를 리스트로. "다르면 [편집]에서 수정하세요"
- 하단: **💾 저장** 버튼(컨펌 닫기 + toast) + **✏️ 편집**(edit mode 전환) 버튼. 실행은 편집창(`WorkflowEditPane`)의 **▶ 실행** 버튼 경유. (2026-06-03 팀장 지시 변경 — PR #340)

**수용 기준:** explanation이 있는 result 프레임 수신 시 컨펌 카드에 단계·권한·가정이 보이고, 권한 박스가 항상 노출된다. explanation이 없으면(레거시) 기존 단순 메시지로 graceful fallback.

---

## 5. 작업 순서 & PR 분할

> Phase별 smoke 검증 원칙(`phase_by_phase_smoke`): 각 PR은 단위테스트 + staging smoke 통과 후 다음으로.

| PR | 범위 | 의존 |
|----|------|------|
| **PR-1** | 영역 A (common_schemas 타입 + codegen) | 없음 — 먼저 머지 |
| **PR-2** | 영역 B (도메인 서비스 + 단위테스트) | PR-1 |
| **PR-3** | 영역 C (composer wiring) | PR-2. 머지 후 **agent-composer Modal 재배포** + staging e2e |
| **PR-4** | 영역 D (프론트 컨펌 카드) | PR-1(타입), PR-3(payload). 프론트 재배포 |

- PR-3 머지 후 **composer 재배포 필수** (`code_change_deploy_verify`). 배포 없이 두면 다음 배포 때 surprise.
- PR-1은 `common_schemas` 버전 bump → 이를 dep으로 쓰는 모듈들 lock 갱신 확인.

---

## 5-1. QA 검증 완료 체크리스트 (PR #340 추가, 2026-06-03)

ConfirmCard 직전 채팅창에 AI 검증 완료 보고서를 `ChatMessageFrame`으로 emit한다.

**구현 위치:** `composer_graph._build_qa_checklist(state)` static 메서드

**표시 항목:**
| # | 항목 | 데이터 출처 |
|---|------|------------|
| ① | 의도 분석 | `intent`, `draft_spec.natural_language_intent`, `intent_analyzed_entities` |
| ② | 노드 선출 | `node_candidates` 수, `workflow_draft.nodes` 최종 선정 |
| ③ | 워크플로우 작성 | 노드 수, 연결 수, DAG 검증 완료 |
| ④ | QA 품질 평가 통과 | `qa_score`, `qa_feedback` |

**emit 순서:** `ChatMessageFrame(qa_checklist)` → `ResultFrame(propose)` (ConfirmCard)

---

## 6. 범위 밖 (이번 작업 아님 — 별도 논의)

- **토큰 단위 타이핑(Zapier식)**: `LLMPort`/llm-base 스트리밍 도입 필요. 별개 작업. 이번엔 summary를 `ChatMessageFrame` 한 번에 emit(타이핑 효과 없음).
- **assumptions 고도화**: 현재는 default 비교 기반. 더 정확히 하려면 `drafter_node`가 가정을 명시적으로 기록하게 개조 — 후속.
- **실행 전 dry-run 미리보기**: 사이드이펙트 없이 샘플 실행. 후속 아이디어.

---

## 7. 리스크 & 가드

| 리스크 | 가드 |
|--------|------|
| LLM이 사실과 다른 summary 생성 | summary만 LLM, 나머지(steps/permissions/assumptions)는 결정론. summary 실패 시 템플릿 fallback |
| `node_registry.get_schema` 추가 호출로 지연 | `state["node_candidates"]` 우선 재사용, 누락분만 조회 |
| common_schemas 버전 bump 후 의존 모듈 깨짐 | PR-1 단독 머지 + lock 갱신 확인 |
| 레거시 result 프레임(explanation 없음) | 프론트·payload 양쪽 graceful fallback 명시 |
| composer 재배포 누락 | PR-3 머지 직후 재배포 체크리스트 |

---

## 8. 완료 정의 (DoD)

- [x] `WorkflowExplanation` common_schemas export + 프론트 타입 생성
- [x] 도메인 서비스 단위테스트 통과 (LLM 없이 결정론 추출)
- [x] composer e2e: 최종 result 프레임 payload에 explanation 포함
- [ ] staging에서 실제 초안 생성 → 컨펌 카드에 단계/권한/가정 표시 확인 (Modal 에러로 미확인)
- [x] 권한 매니페스트 박스 항상 노출, high/medium risk 시각 강조
- [x] explanation 없는 레거시 응답도 깨지지 않음
- [x] ConfirmCard 버튼: 💾 저장 + ✏️ 편집 (PR #340, 2026-06-03)
- [x] QA 검증 완료 체크리스트 ChatMessageFrame emit (PR #340, 2026-06-03)
