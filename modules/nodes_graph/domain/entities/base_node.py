from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from .node_metadata import NodeMetadata

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class BaseNode(Generic[TInput, TOutput], ABC):
    """모든 노드의 추상 기본 클래스. 53종 노드가 이 클래스를 상속하여 process()를 구현한다."""

    metadata: NodeMetadata
    input_schema: type[TInput]
    output_schema: type[TOutput]

    @abstractmethod
    async def process(self, input: TInput) -> TOutput:
        """노드 로직 실행. Input → Output 변환."""
        ...
