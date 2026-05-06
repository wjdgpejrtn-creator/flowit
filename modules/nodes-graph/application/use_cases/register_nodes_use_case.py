from __future__ import annotations

from ...domain.entities.node_definition import NodeDefinition
from ...domain.ports.embedder_port import EmbedderPort
from ...domain.ports.node_definition_repository import NodeDefinitionRepository


class RegisterNodesUseCase:
    """Plugin discovery로 노드를 일괄 등록하는 유스케이스."""

    def __init__(self, node_def_repo: NodeDefinitionRepository, embedder: EmbedderPort) -> None:
        self._repo = node_def_repo
        self._embedder = embedder

    async def execute(self, nodes: list[NodeDefinition]) -> int:
        """
        1. embedding이 없는 노드에 대해 embed(description) 호출
        2. node_def_repo.upsert(definition) 호출
        3. 등록된 건수 반환
        """
        texts = [n.description for n in nodes if n.embedding is None]
        embeddings = await self._embedder.embed_batch(texts) if texts else []

        embed_iter = iter(embeddings)
        registered = 0
        for node in nodes:
            if node.embedding is None:
                node.embedding = next(embed_iter)
            await self._repo.upsert(node)
            registered += 1

        return registered
