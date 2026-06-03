"""skill_templates 순수 헬퍼 단위 테스트 (REQ-010, B1 후속).

`_format_fields` — seed property dict → 'name: description' 나열. #341 seed description을
SOP 합성 본문에 실어 extract LLM 힌트로 재주입하는 경로의 핵심 헬퍼. 라우터/프록시 없이
순수 함수만 직접 검증한다(합성 경로 통합은 test_routes_skills_extract.py가 커버).
"""
from __future__ import annotations

from app.services.skill_templates import _format_fields, _node_to_sop_markdown

# ── _format_fields ───────────────────────────────────────────────────────────


def test_format_fields_empty_returns_none_label():
    assert _format_fields({}) == "없음"


def test_format_fields_with_description_emits_name_colon_desc():
    props = {"audience_segment_id": {"type": "string", "description": "대상 세그먼트 ID. 예: SEG-1234"}}
    assert _format_fields(props) == "audience_segment_id: 대상 세그먼트 ID. 예: SEG-1234"


def test_format_fields_without_description_emits_name_only():
    assert _format_fields({"campaign_id": {"type": "string"}}) == "campaign_id"


def test_format_fields_joins_multiple_with_semicolon():
    props = {
        "a": {"type": "string", "description": "에이"},
        "b": {"type": "number"},
        "c": {"type": "string", "description": "씨"},
    }
    # 순서 보존(dict 삽입 순서) + '; ' 구분 + description 유무 혼합
    assert _format_fields(props) == "a: 에이; b; c: 씨"


def test_format_fields_non_dict_spec_is_guarded():
    # 비정상 spec(스키마 깨짐)도 크래시 없이 이름만 — 방어성
    assert _format_fields({"weird": "not-a-dict", "ok": {"description": "정상"}}) == "weird; ok: 정상"


def test_format_fields_empty_string_description_emits_name_only():
    # description이 빈 문자열이면(falsy) 이름만 — 'name: ' 꼬리 방지
    assert _format_fields({"x": {"type": "string", "description": ""}}) == "x"


# ── _node_to_sop_markdown (description 전파 1건) ──────────────────────────────


def test_node_to_sop_markdown_carries_field_description():
    node = {
        "name": "캠페인 스케줄링",
        "description": "캠페인 자동 발송",
        "category": "trigger",
        "risk_level": "Medium",
        "required_connections": ["google"],
        "inputs": {
            "type": "object",
            "properties": {
                "audience_segment_id": {"type": "string", "description": "대상 세그먼트 ID. 예: SEG-1234"},
            },
        },
        "outputs": {"type": "object", "properties": {"scheduled_at": {"type": "string"}}},
    }
    md = _node_to_sop_markdown(node)
    # 입력 라인에 필드명 + seed description이 함께 실려야(LLM 힌트)
    assert "audience_segment_id: 대상 세그먼트 ID. 예: SEG-1234" in md
    # 연동/위험도 메타도 유지
    assert "필요 연동: google" in md
