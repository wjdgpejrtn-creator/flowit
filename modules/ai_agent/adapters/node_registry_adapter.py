from __future__ import annotations

from uuid import UUID

from common_schemas import NodeConfig
from nodes_graph.application.executable_node_types import EXECUTABLE_NODE_TYPES
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ..domain.ports.node_registry import NodeRegistry

# search()가 실행 불가 후보를 거른 뒤에도 limit을 채우도록 넉넉히 당겨온다(과거 게시 스킬
# NodeDefinition 오염 등 비실행 항목이 top-k를 잠식하는 경우 대비, #378).
_OVERFETCH_FACTOR = 4

# 구조 노드 = 트리거 + 제어흐름. 사용자 문장에 자연어로 녹아(예: "매주 월요일 9시") 의미검색
# top-k에 안 떠서 항상 후보로 노출해야 하는 카테고리(#378 후속 A). category로 자동판별 —
# 새 트리거/제어 노드가 추가돼도 별도 유지보수 없이 포함된다. (제어흐름 노드의 category는
# 디렉토리명 'control'이 아니라 실제 필드값 'condition'임에 유의 — nodes_graph 카탈로그 기준.)
_STRUCTURAL_CATEGORIES = frozenset({"trigger", "condition"})


class NodeRegistryAdapter(NodeRegistry):
    """NodeRegistry 구현 — nodes_graph.NodeDefinitionRepository + EmbedderPort Facade.

    ai_agent는 NodeDefinitionRepository에 직접 의존하지 않고 이 어댑터를 통해서만 접근.
    검색 경로: query → BGE-M3 임베딩 → pgvector cosine similarity → NodeConfig 변환.
    """

    def __init__(
        self,
        repo: NodeDefinitionRepository,
        embedder: EmbedderPort,
    ) -> None:
        self._repo = repo
        self._embedder = embedder

    async def search(self, query: str, limit: int = 10) -> list[NodeConfig]:
        embedding = await self._embedder.embed(query)
        # 실행 불가 node_type(예: 과거 게시 스킬이 카탈로그에 남긴 도메인 NodeDefinition)은
        # drafter가 쓰면 실행 시 "카탈로그 미등록 node_type"으로 실패한다(#378). 그라운딩 가드:
        # 실행 클래스가 있는 node_type만 후보로 통과시킨다. 거른 뒤에도 limit을 채우도록
        # over-fetch 후 slice.
        definitions = await self._repo.search_by_embedding(embedding, limit=limit * _OVERFETCH_FACTOR)
        executable = [d for d in definitions if d.node_type in EXECUTABLE_NODE_TYPES]
        return [self._to_config(d) for d in executable[:limit]]

    async def get_schema(self, node_id: UUID) -> NodeConfig:
        definition = await self._repo.get_by_id(node_id)
        if definition is None:
            raise KeyError(f"NodeDefinition not found: {node_id}")
        return self._to_config(definition)

    async def list_structural(self) -> list[NodeConfig]:
        # 카탈로그 전체에서 트리거/제어흐름 category만 추린다. search()와 동일하게 실행 클래스가
        # 있는 node_type만 통과시켜(오염 행 가드) drafter가 실행 불가 노드를 못 쓰게 한다(#378).
        definitions = await self._repo.list_all()
        structural = [
            d
            for d in definitions
            if d.category in _STRUCTURAL_CATEGORIES and d.node_type in EXECUTABLE_NODE_TYPES
        ]
        return [self._to_config(d) for d in structural]

    async def list_by_node_types(self, node_types: list[str]) -> list[NodeConfig]:
        # CAN_FOLLOW 확장이 회수한 후행 node_type을 NodeConfig로 그라운딩 (ADR-0026 §4.2a).
        # search()/list_structural()과 동일한 실행가능 가드 — 카탈로그 오염 행(과거 게시 스킬
        # NodeDefinition 등)이 후보로 새지 않게 EXECUTABLE_NODE_TYPES만 통과시킨다.
        wanted = set(node_types)
        if not wanted:
            return []
        definitions = await self._repo.list_all()
        matched = [
            d for d in definitions
            if d.node_type in wanted and d.node_type in EXECUTABLE_NODE_TYPES
        ]
        return [self._to_config(d) for d in matched]

    @staticmethod
    def _to_config(d: NodeDefinition) -> NodeConfig:
        return NodeConfig(
            node_id=d.node_id,
            node_type=d.node_type,
            name=d.name,
            category=d.category,
            version=d.version,
            input_schema=d.input_schema,
            output_schema=d.output_schema,
            parameter_schema=d.parameter_schema,
            risk_level=d.risk_level,
            required_connections=d.required_connections,
            description=d.description,
            is_mvp=d.is_mvp,
        )
