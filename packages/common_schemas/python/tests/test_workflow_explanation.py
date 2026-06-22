"""WorkflowExplanation / ExplanationStep / PermissionItem 단위 테스트."""
import pytest
from common_schemas import ExplanationStep, PermissionItem, WorkflowExplanation
from common_schemas.enums import RiskLevel
from pydantic import ValidationError


def test_minimal_explanation_defaults():
    """필수 필드만 주면 리스트 필드는 빈 리스트로 기본값."""
    exp = WorkflowExplanation(
        intent_restatement="매주 월요일 광고 시트를 요약해 Slack으로 보낸다",
        summary="이 워크플로우는 매주 광고 데이터를 요약해 Slack에 전송합니다.",
    )
    assert exp.steps == []
    assert exp.permissions == []
    assert exp.assumptions == []


def test_full_explanation_roundtrip():
    """전체 필드 채운 뒤 직렬화 → 역직렬화 동일성."""
    exp = WorkflowExplanation(
        intent_restatement="광고 시트 요약 후 Slack 전송",
        summary="요약 후 전송.",
        steps=[
            ExplanationStep(
                order=1, node_name="Google Sheets 읽기", description="시트 데이터 로드", risk_level=RiskLevel.LOW
            ),
            ExplanationStep(
                order=2, node_name="Slack 전송", description="채널에 메시지 전송", risk_level=RiskLevel.MEDIUM
            ),
        ],
        permissions=[
            PermissionItem(connection="google_sheets", node_name="Google Sheets 읽기", risk_level=RiskLevel.LOW),
            PermissionItem(connection="slack", node_name="Slack 전송", risk_level=RiskLevel.MEDIUM),
        ],
        assumptions=["전송 시각: 09:00 (기본값)"],
    )
    dumped = exp.model_dump(mode="json")
    restored = WorkflowExplanation.model_validate(dumped)
    assert restored == exp
    assert dumped["steps"][1]["risk_level"] == "Medium"


def test_frozen_immutability():
    """frozen=True — 필드 변경 시 에러."""
    step = ExplanationStep(order=1, node_name="n", description="d", risk_level=RiskLevel.LOW)
    with pytest.raises(ValidationError):
        step.order = 2


def test_missing_required_field_raises():
    """필수 필드 누락 시 ValidationError."""
    with pytest.raises(ValidationError):
        WorkflowExplanation(summary="설명만 있고 intent 없음")  # type: ignore[call-arg]
