"""워크플로우 설명 — 컨펌 게이트 신뢰 매니페스트 (confirm-gate-explanation).

one-shot(HITL 없음) 철학에서 신뢰는 최종 컨펌 게이트 한 곳에 몰린다. AI 초안을
실행하기 전에 "무엇을 하고(steps), 무엇을 건드리며(permissions), 무엇을 가정했는지
(assumptions)"를 사용자에게 보여주기 위한 구조화 설명.

- steps/permissions/assumptions는 `WorkflowSchema` + `NodeConfig`에서 **결정론적으로
  추출**된 사실이다 (LLM 자유 서술 금지 — 그래프와 어긋난 설명은 신뢰를 파괴한다).
- summary 한 문장만 LLM이 다듬을 수 있다 (선택적).
- ResultFrame.payload["explanation"]에 직렬화되어 orchestrator→api→프론트로 흐른다.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import RiskLevel


class ExplanationStep(BaseModel):
    """워크플로우 실행 단계 1개 — 노드 하나에 대응."""

    model_config = ConfigDict(frozen=True)

    order: int  # 1-based 실행 순서
    node_name: str  # NodeConfig.name
    description: str  # NodeConfig.description (또는 LLM이 다듬은 한 줄)
    risk_level: RiskLevel


class PermissionItem(BaseModel):
    """워크플로우가 요구하는 외부 연결(권한) 1건 — required_connections 원소."""

    model_config = ConfigDict(frozen=True)

    connection: str  # required_connections 원소 (예: "slack", "google_sheets")
    node_name: str  # 이 권한을 요구하는 노드
    risk_level: RiskLevel  # 해당 노드 risk → 쓰기/위험 강조용


class WorkflowExplanation(BaseModel):
    """컨펌 게이트에서 보여줄 워크플로우 설명 매니페스트.

    intent_restatement / steps / permissions / assumptions는 사실 기반(결정론).
    summary만 LLM 다듬기 허용.
    """

    model_config = ConfigDict(frozen=True)

    intent_restatement: str  # ① 의도 재진술 (사용자 요청 미러링)
    summary: str  # 평문 한 단락 (LLM 다듬음 또는 템플릿)
    steps: list[ExplanationStep] = Field(default_factory=list)  # ② 단계별 설명
    permissions: list[PermissionItem] = Field(default_factory=list)  # ③ 권한 매니페스트 (connection dedup)
    assumptions: list[str] = Field(default_factory=list)  # ④ 가정·기본값 선언
