from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from common_schemas.workflow import NodeInstance


class ExecutionLevel(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: int
    nodes: list[NodeInstance]
