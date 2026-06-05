from __future__ import annotations

from typing import Literal

from common_schemas.workflow import Edge
from pydantic import BaseModel, ConfigDict

from .execution_level import ExecutionLevel


class LoopBody(BaseModel):
    """유한 순환(ADR-0023 L3)의 루프 바디 — 하나의 non-trivial SCC.

    바디는 back-edge를 제거한 sub-DAG라 ``levels``로 펼쳐 iteration마다 1회씩 실행한다.
    한 iteration 완료 후 ``back_edges``의 소스 출력을 평가해(live면 재반복) 지속/탈출을 정한다.
    가드(``max_iterations``) 도달 시 ``exit_edges``를 강제 live로 표시해 하류로 진행한다.
    """

    model_config = ConfigDict(frozen=True)

    levels: list[ExecutionLevel]
    back_edges: list[Edge]
    exit_edges: list[Edge]
    max_iterations: int


class ExecutionStep(BaseModel):
    """응축 DAG의 실행 단위 — 단발 레벨(``level``) 또는 루프 바디(``loop``).

    비순환 워크플로우는 전부 ``kind="level"`` 스텝이라 기존 레벨 실행과 동일하다.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["level", "loop"]
    level: ExecutionLevel | None = None
    loop: LoopBody | None = None
