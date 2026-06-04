"""ReferenceResolver 단위 테스트 — ${상류.출력} 참조 해석 (ADR-0023 L1)."""
from __future__ import annotations

from src.domain.services.reference_resolver import ReferenceResolver

NID = "11111111-1111-1111-1111-111111111111"
OUTPUTS = {NID: {"summary": "요약본", "score": 9, "rows": [1, 2, 3], "meta": {"k": "v"}}}


def _r():
    return ReferenceResolver()


def test_full_value_ref_preserves_type_string():
    out = _r().resolve_params({"text": f"${{{NID}.summary}}"}, OUTPUTS)
    assert out["text"] == "요약본"


def test_full_value_ref_preserves_type_int():
    out = _r().resolve_params({"threshold": f"${{{NID}.score}}"}, OUTPUTS)
    assert out["threshold"] == 9
    assert isinstance(out["threshold"], int)


def test_full_value_ref_preserves_type_list_and_dict():
    out = _r().resolve_params(
        {"rows": f"${{{NID}.rows}}", "meta": f"${{{NID}.meta}}"}, OUTPUTS
    )
    assert out["rows"] == [1, 2, 3]
    assert out["meta"] == {"k": "v"}


def test_embedded_ref_interpolates_to_string():
    out = _r().resolve_params({"text": f"요약: ${{{NID}.summary}} (점수 ${{{NID}.score}})"}, OUTPUTS)
    assert out["text"] == "요약: 요약본 (점수 9)"


def test_non_ref_passthrough():
    out = _r().resolve_params({"text": "그냥 문자열", "n": 5, "b": True}, OUTPUTS)
    assert out == {"text": "그냥 문자열", "n": 5, "b": True}


def test_unresolved_full_ref_degrades_to_none():
    out = _r().resolve_params({"text": f"${{{NID}.missing}}"}, OUTPUTS)
    assert out["text"] is None


def test_unresolved_embedded_ref_degrades_to_empty():
    out = _r().resolve_params({"text": f"x${{{NID}.missing}}y"}, OUTPUTS)
    assert out["text"] == "xy"


def test_unknown_node_unresolved():
    out = _r().resolve_params({"text": "${99999999-0000-0000-0000-000000000000.summary}"}, OUTPUTS)
    assert out["text"] is None


def test_nested_list_and_dict_resolved():
    out = _r().resolve_params(
        {"channels": [f"${{{NID}.summary}}", "lit"], "cfg": {"v": f"${{{NID}.score}}"}}, OUTPUTS
    )
    assert out["channels"] == ["요약본", "lit"]
    assert out["cfg"] == {"v": 9}


def test_ref_without_field_is_unresolved():
    out = _r().resolve_params({"text": f"${{{NID}}}"}, OUTPUTS)
    assert out["text"] is None
