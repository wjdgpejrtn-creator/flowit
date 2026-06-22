"""dataflow_grounding — compose 시점 ref 경로 grounding 순수 단위테스트.

Phase 1(정혜): 첫 세그먼트 존재성 + array/primitive 필드접근 절단. 깊은 객체 경로(Phase 2,
스키마 properties 보강 후)는 보수적 보존. → [REQ-004 / nodes_graph 분담]
"""
from __future__ import annotations

from uuid import uuid4

from common_schemas import NodeConfig
from common_schemas.enums import RiskLevel

from ai_agent.domain.services.dataflow_grounding import (
    ground_ref_fields,
    output_field_types,
    outputs_of,
)

_IID = uuid4()


def _ref(path: str) -> str:
    return f"${{{_IID}.{path}}}"


class TestGroundRefFieldsPhase1:
    def test_valid_single_field_kept(self):
        fields = {_IID: {"content": "string"}}
        assert ground_ref_fields(_ref("content"), fields) == _ref("content")

    def test_head_missing_single_output_corrected(self):
        # head가 없고 출력이 정확히 1개 → 그 단일 필드로 보정(환각 suffix 제거).
        fields = {_IID: {"content": "string"}}
        assert ground_ref_fields(_ref("text"), fields) == _ref("content")
        assert ground_ref_fields(_ref("text.foo"), fields) == _ref("content")

    def test_head_missing_multi_output_kept(self):
        # head 없고 출력 2개↑ → 보정 불가, 원본 보존(런타임 degrade / validator reject).
        fields = {_IID: {"values": "array", "row_count": "integer"}}
        assert ground_ref_fields(_ref("items"), fields) == _ref("items")

    def test_array_nested_field_access_truncated(self):
        # ⭐ 버그 직격: sheets.values(2D array)에 .email 접근 → 객체 아니라 필드접근 불가
        # → head(values)까지 절단해 배열 자체 전달. to=None 환각 차단.
        fields = {_IID: {"values": "array", "row_count": "integer"}}
        assert ground_ref_fields(_ref("values.email"), fields) == _ref("values")

    def test_primitive_nested_field_access_truncated(self):
        fields = {_IID: {"message_id": "string"}}
        assert ground_ref_fields(_ref("message_id.foo"), fields) == _ref("message_id")

    def test_object_nested_preserved_for_phase2(self):
        # head 타입이 object → 깊은 경로 검증은 Phase 2(스키마 properties 보강 후) → 보수적 보존.
        fields = {_IID: {"payload": "object"}}
        assert ground_ref_fields(_ref("payload.user.email"), fields) == _ref("payload.user.email")

    def test_unknown_type_nested_preserved(self):
        # 타입 미선언("") → 보수적 보존(과교정 방지).
        fields = {_IID: {"result": ""}}
        assert ground_ref_fields(_ref("result.x"), fields) == _ref("result.x")

    def test_nested_inside_list_value(self):
        # gmail to=["${sheets.values.email}"] 같은 리스트 안 ref도 재귀 처리.
        fields = {_IID: {"values": "array"}}
        assert ground_ref_fields([_ref("values.email")], fields) == [_ref("values")]

    def test_unknown_node_untouched(self):
        # 맵에 없는 instance → 손대지 않음.
        assert ground_ref_fields(_ref("anything.x"), {}) == _ref("anything.x")

    def test_non_uuid_token_untouched(self):
        assert ground_ref_fields("${notauuid.field}", {_IID: {"content": "string"}}) == "${notauuid.field}"

    def test_plain_string_without_ref_unchanged(self):
        assert ground_ref_fields("그냥 텍스트", {_IID: {"content": "string"}}) == "그냥 텍스트"


def _cfg(output_props: dict) -> NodeConfig:
    return NodeConfig(
        node_id=uuid4(), node_type="t", name="t", category="test", version="1.0",
        description="", input_schema={}, output_schema={"properties": output_props},
        parameter_schema={}, risk_level=RiskLevel.LOW, required_connections=[], is_mvp=True,
    )


class TestOutputFieldTypes:
    def test_maps_name_to_json_type(self):
        cfg = _cfg({"values": {"type": "array"}, "row_count": {"type": "integer"}})
        assert output_field_types(cfg) == {"values": "array", "row_count": "integer"}

    def test_missing_type_becomes_empty_string(self):
        cfg = _cfg({"result": {}})
        assert output_field_types(cfg) == {"result": ""}

    def test_outputs_of_still_returns_names(self):
        cfg = _cfg({"a": {"type": "string"}, "b": {"type": "array"}})
        assert outputs_of(cfg) == ["a", "b"]
