from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ${<instance_id>.<output_field>} — instance_id는 UUID(점 없음)라 첫 '.' 기준 분리.
_REF_RE = re.compile(r"\$\{([^}]+)\}")


class ReferenceResolver:
    """노드 파라미터의 ``${<instance_id>.<field>}`` 참조를 상류 노드 출력으로 해석한다 (ADR-0023 L1).

    데이터 흐름의 핵심: 엣지는 순서/의존을, 참조는 데이터 매핑을 담당한다(직교).

    해석 규칙:
    - **값 전체가 단일 참조**면 상류 출력의 **타입을 보존**(객체·숫자·리스트 그대로).
    - **문자열 내 임베디드 참조**는 ``str()`` 보간(부분 문자열 합성 지원).
    - 미해결(상류 누락/필드 없음)은 전체값=None, 임베디드="" 로 degrade하고 경고 로깅
      (한 노드 실패가 전체 실행을 깨지 않도록 — graceful degrade).

    순수 도메인 서비스(I/O·프레임워크 의존 없음).
    """

    def resolve_params(
        self, parameters: dict[str, Any], node_outputs: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """``parameters`` 내 모든 참조를 ``node_outputs``(str(instance_id) → 출력 dict)로 해석."""
        return {k: self._resolve_value(v, node_outputs) for k, v in parameters.items()}

    def _resolve_value(self, value: Any, node_outputs: dict[str, dict[str, Any]]) -> Any:
        if isinstance(value, str):
            return self._resolve_string(value, node_outputs)
        if isinstance(value, list):
            return [self._resolve_value(v, node_outputs) for v in value]
        if isinstance(value, dict):
            return {k: self._resolve_value(v, node_outputs) for k, v in value.items()}
        return value

    def _resolve_string(self, text: str, node_outputs: dict[str, dict[str, Any]]) -> Any:
        full = _REF_RE.fullmatch(text.strip())
        if full is not None:
            # 값 전체가 단일 참조 — 타입 보존
            resolved, found = self._lookup(full.group(1), node_outputs)
            if not found:
                logger.warning("미해결 참조(전체값) — None으로 degrade: %s", text)
                return None
            return resolved

        # 임베디드 참조 — 문자열 보간
        def _sub(m: re.Match[str]) -> str:
            resolved, found = self._lookup(m.group(1), node_outputs)
            if not found:
                logger.warning("미해결 참조(임베디드) — 빈 문자열로 degrade: %s", m.group(0))
                return ""
            return str(resolved)

        return _REF_RE.sub(_sub, text)

    @staticmethod
    def _lookup(inner: str, node_outputs: dict[str, dict[str, Any]]) -> tuple[Any, bool]:
        """``<instance_id>.<field>`` → (값, 해결여부). instance_id는 첫 '.' 앞."""
        node_id, sep, field = inner.partition(".")
        if not sep or not field:
            return None, False
        out = node_outputs.get(node_id.strip())
        if out is None or field not in out:
            return None, False
        return out[field], True
