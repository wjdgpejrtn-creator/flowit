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


def ground_ref_fields(value: Any, outputs_by_instance: dict[UUID, list[str]]) -> Any:
    """``${<instance_id>.<field>}`` 참조의 ``<field>``를 상류 노드의 실제 출력 필드에 grounding.

    `rewrite_refs` 이후(토큰이 이미 instance_id로 치환된 상태) 호출한다. LLM이 존재하지 않는
    출력 필드를 환각하는 것(예: 출력이 ``[scheduled_at, ...]``인데 ``.values`` 참조)을 방어:

    - 참조 노드의 출력 필드 집합에 ``<field>``가 있으면 그대로 둔다.
    - 없고 그 노드의 출력이 **정확히 1개**면 그 단일 필드로 보정한다(거의 확실히 의도한 필드).
    - 없고 출력이 0개 또는 2개 이상이면(어느 필드인지 결정 불가) 원본을 보존하고 경고만 남긴다
      — 런타임 ReferenceResolver가 미해결로 graceful degrade한다. 잘못된 **소스 노드 선택**은
      의미 판단이라 결정론적으로 고칠 수 없으므로 로그로만 노출한다.
    - 토큰이 instance_id가 아니거나(미해결 토큰) 맵에 없는 노드면 손대지 않는다.
    """
    if isinstance(value, str):
        def _sub(m: re.Match[str]) -> str:
            token, field = m.group(1), m.group(2)
            try:
                inst = UUID(token)
            except ValueError:
                return m.group(0)
            outs = outputs_by_instance.get(inst)
            if outs is None or field in outs:
                return m.group(0)
            if len(outs) == 1:
                _logger.warning("ref 필드 보정: %s.%s → %s.%s", token, field, token, outs[0])
                return f"${{{token}.{outs[0]}}}"
            _logger.warning(
                "ref 필드 미존재(보정 불가, graceful degrade): %s.%s (outputs=%s)", token, field, outs
            )
            return m.group(0)
        return _REF_TOKEN_RE.sub(_sub, value)
    if isinstance(value, list):
        return [ground_ref_fields(v, outputs_by_instance) for v in value]
    if isinstance(value, dict):
        return {k: ground_ref_fields(v, outputs_by_instance) for k, v in value.items()}
    return value


def outputs_of(nc: NodeConfig) -> list[str]:
    """NodeConfig의 출력 필드명 목록 (output_schema.properties 키)."""
    return list((nc.output_schema or {}).get("properties", {}).keys())
