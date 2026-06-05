from __future__ import annotations

from typing import Any


class BranchEvaluator:
    """조건 노드 출력으로 outgoing 엣지의 live 여부를 판정한다 (ADR-0023 L2).

    조건 노드(category ``"condition"``)는 출력의 **데이터 pass-through용 ``value``를 제외한
    string 필드값**으로 live한 출력 핸들을 지정한다 — 실측: ``if_condition`` → ``branch``,
    ``switch_case`` → ``matched_case``. 엣지의 ``from_handle``이 그 값과 일치하면 live.

    degrade(하위호환): selector가 없거나 outgoing 핸들 중 일치하는 게 없으면(레거시
    ``from_handle="output"`` 등) **전부 live**로 처리해 그래프를 고립시키지 않는다.
    """

    _PASSTHROUGH_KEYS = frozenset({"value"})

    def live_handles(self, output: Any, outgoing_handles: list[str]) -> set[str] | None:
        """selector와 일치하는 outgoing 핸들 집합. 분기 비활성이면 ``None``(= 전부 live)."""
        if not isinstance(output, dict):
            return None
        selectors = {
            str(v)
            for k, v in output.items()
            if k not in self._PASSTHROUGH_KEYS and isinstance(v, str)
        }
        active = selectors & set(outgoing_handles)
        return active or None

    def is_edge_live(
        self,
        source_is_brancher: bool,
        source_output: Any,
        source_outgoing_handles: list[str],
        edge_handle: str,
    ) -> bool:
        """엣지 live 여부. 조건 노드가 아니면 항상 live."""
        if not source_is_brancher:
            return True
        live = self.live_handles(source_output, source_outgoing_handles)
        if live is None:
            return True
        return edge_handle in live
