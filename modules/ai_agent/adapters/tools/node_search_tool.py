"""NodeSearchTool — AI Agent 내부용 노드 카탈로그 검색 도구.

toolset BaseTool이 아님. ai_agent 내부(Personalization, Composer 등)에서만 사용.
NodeRegistry Port를 주입받아 nodes_graph 카탈로그를 조회한다.
"""
from __future__ import annotations

from uuid import UUID

from common_schemas import NodeConfig

from ...domain.ports.node_registry import NodeRegistry


class NodeSearchTool:
    """NodeRegistry를 감싸는 ai_agent 내부 노드 검색 유틸리티.

    주요 용도:
    - Workflow Composer retriever_node의 후보 검색
    - Personalization Agent가 사용자 스킬을 현재 카탈로그와 매핑할 때
    - LLM 프롬프트에 노드 목록을 주입할 때 (format_for_prompt)
    """

    def __init__(self, node_registry: NodeRegistry) -> None:
        self._registry = node_registry

    async def search(self, query: str, limit: int = 10) -> list[NodeConfig]:
        """의미 기반 노드 검색 (BGE-M3 임베딩 유사도, NodeRegistryAdapter 위임)."""
        return await self._registry.search(query, limit=limit)

    async def get_schema(self, node_id: UUID) -> NodeConfig:
        """node_id로 노드 스키마 조회. 없으면 KeyError."""
        return await self._registry.get_schema(node_id)

    def format_for_prompt(self, nodes: list[NodeConfig]) -> str:
        """LLM 프롬프트에 삽입할 노드 목록 텍스트 생성.

        반환 예:
            - rest_api: REST API 호출 — HTTP GET/POST/PUT/DELETE 지원
            - email_send: 이메일 발송 — SMTP 기반 알림
        """
        if not nodes:
            return "(사용 가능한 노드 없음)"
        return "\n".join(
            f"- {n.node_type}: {n.name} — {n.description}" for n in nodes
        )
