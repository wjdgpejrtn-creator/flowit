from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from common_schemas import NodeConfig

_logger = logging.getLogger(__name__)

# 데이터 흐름 참조 ${<token>.<field>} — LLM은 token으로 node_type(fresh)/ref(edit)를 쓰고,
# 빌드 시 instance_id로 재작성한다(token엔 점 없음 → 첫 '.'로 분리, ADR-0023 L1).
_REF_TOKEN_RE = re.compile(r"\$\{([^.}]+)\.([^}]+)\}")


def rewrite_refs(value: Any, id_by_token: dict[str, UUID]) -> Any:
    """파라미터 값 내 ``${<token>.<field>}``의 token을 instance_id로 치환.

    token이 맵에 없으면(존재하지 않는 노드 참조) 원본을 보존한다 — 실행 시점
    ReferenceResolver가 미해결로 graceful degrade한다.
    """
    if isinstance(value, str):
        def _sub(m: re.Match[str]) -> str:
            token, field = m.group(1), m.group(2)
            inst = id_by_token.get(token)
            return f"${{{inst}.{field}}}" if inst is not None else m.group(0)
        return _REF_TOKEN_RE.sub(_sub, value)
    if isinstance(value, list):
        return [rewrite_refs(v, id_by_token) for v in value]
    if isinstance(value, dict):
        return {k: rewrite_refs(v, id_by_token) for k, v in value.items()}
    return value


# nested 필드 접근(.subfield)이 불가능한 출력 타입 — 객체가 아니므로 키 접근 불가.
# object/미정의(공백)는 깊은 경로 검증(Phase 2, 스키마 properties 보강) 영역이라 보수적 보존.
_NON_OBJECT_TYPES = frozenset({"array", "string", "integer", "number", "boolean"})


def ground_ref_fields(value: Any, fields_by_instance: dict[UUID, dict[str, str]]) -> Any:
    """``${<instance_id>.<path>}`` 참조 경로를 상류 노드 출력 스키마에 grounding(compose 시점).

    `rewrite_refs` 이후(토큰이 instance_id로 치환된 상태) 호출한다. ``fields_by_instance``는
    instance_id → {출력필드명: JSON타입} 맵. LLM이 환각한 출력 경로를 **첫 세그먼트(head)** 기준
    으로 방어한다 (깊은 nested 검증은 Phase 2 — 62종 output_schema properties 보강 후):

    - head가 출력에 있고 단일 필드(rest 없음) → 그대로.
    - head가 출력에 없고 출력이 **정확히 1개** → 그 단일 필드로 보정(환각한 nested suffix 제거).
    - head가 출력에 없고 0/2개↑ → 보정 불가, 원본 보존 + 경고(런타임 degrade; validator가 reject).
    - head가 있으나 **array/primitive인데 .subfield 접근**(rest 존재) → 객체가 아니라 필드접근
      불가 → head까지 절단(``${id.head}``)해 값 자체를 전달 + 경고. (예: ``sheets.values.email``
      → ``sheets.values`` — to=None 환각 차단)
    - head 타입이 object/미정의이고 rest 존재 → 깊은 경로 검증은 Phase 2 → 보수적 보존.
    - 토큰이 instance_id 아님/맵에 없는 노드면 손대지 않는다.
    """
    if isinstance(value, str):
        def _sub(m: re.Match[str]) -> str:
            token, path = m.group(1), m.group(2)
            try:
                inst = UUID(token)
            except ValueError:
                return m.group(0)
            fields = fields_by_instance.get(inst)
            if fields is None:
                return m.group(0)
            head, _, rest = path.partition(".")
            if head in fields:
                if rest and fields.get(head) in _NON_OBJECT_TYPES:
                    _logger.warning(
                        "ref 비객체 필드접근 절단: %s.%s (%s=%s) → %s.%s",
                        token, path, head, fields.get(head), token, head,
                    )
                    return f"${{{token}.{head}}}"
                return m.group(0)  # 유효 단일 필드 또는 object/미정의 nested(Phase 2 보존)
            if len(fields) == 1:
                only = next(iter(fields))
                _logger.warning("ref 필드 보정: %s.%s → %s.%s", token, path, token, only)
                return f"${{{token}.{only}}}"
            _logger.warning(
                "ref 경로 head 미존재(보정 불가, graceful degrade): %s.%s (outputs=%s)",
                token, path, list(fields),
            )
            return m.group(0)
        return _REF_TOKEN_RE.sub(_sub, value)
    if isinstance(value, list):
        return [ground_ref_fields(v, fields_by_instance) for v in value]
    if isinstance(value, dict):
        return {k: ground_ref_fields(v, fields_by_instance) for k, v in value.items()}
    return value


def outputs_of(nc: NodeConfig) -> list[str]:
    """NodeConfig의 출력 필드명 목록 (output_schema.properties 키) — LLM 출력 힌트용."""
    return list((nc.output_schema or {}).get("properties", {}).keys())


def output_field_types(nc: NodeConfig) -> dict[str, str]:
    """NodeConfig 출력 필드명 → JSON 타입 맵 (ground_ref_fields 첫 세그먼트/타입 검증용).

    타입 미선언 필드는 빈 문자열("") — ground_ref_fields가 보수적으로(보존) 처리한다.
    """
    props = (nc.output_schema or {}).get("properties", {}) or {}
    return {name: (spec or {}).get("type", "") for name, spec in props.items()}
