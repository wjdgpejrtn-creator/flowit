from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from common_schemas.workflow import NodeConfig, NodeInstance


class NodeExecutorPort(ABC):

    @abstractmethod
    def execute(
        self,
        node: NodeInstance,
        config: NodeConfig,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        ...
