"""Plugin discovery 진입점 — 카탈로그 자동 등록 + 임베딩 + UPSERT.

Sprint 3 plan §4.2 5/14 산출물.
설계 노트 (`plan/sprint-3-catalog-plugin-discovery.md`) §3에서 채택한 패턴:
- **옵션 A (명시 import)** — 추적·테스트 용이성 우선. Sprint 4+에서 pkgutil 자동발견(옵션 B) 재검토.

사용처:
- api_server startup lifespan에서 호출하여 부팅 시 카탈로그 등록 (황대원 5/12-13 작업)
- 운영 스크립트 `scripts/register_catalog.py` 수동 호출
- Skills Builder의 `BuildFromSOPUseCase` / `BuildFromIndustryDefaultUseCase`는 동일한
  RegisterNodesUseCase를 직접 호출 — 본 모듈은 카탈로그 전체 일괄 등록 전용 진입점

EmbedderPort 의존:
- 5/12 저녁 신정혜의 `llm-base` Modal 배포 후 ModalEmbeddingAdapter 가용
- 슬립 시 fake/stub embedder(zeros 768d) 사용 가능
"""
from __future__ import annotations

from ...application.catalog_registry import get_all_node_definitions
from ...application.use_cases.register_nodes_use_case import RegisterNodesUseCase
from ...domain.entities.node_definition import NodeDefinition
from ...domain.ports.embedder_port import EmbedderPort
from ...domain.ports.node_definition_repository import NodeDefinitionRepository


def discover_node_definitions() -> list[NodeDefinition]:
    """카탈로그 전체 NodeDefinition을 발견하여 반환 (등록 없이 조회만).

    옵션 A — 명시 import. `application.catalog_registry.get_all_node_definitions`을 위임.
    """
    return get_all_node_definitions()


async def discover_and_register(
    repo: NodeDefinitionRepository,
    embedder: EmbedderPort,
) -> int:
    """카탈로그 발견 + 임베딩 + UPSERT 일괄 처리.

    Args:
        repo: NodeDefinitionRepository 구현체 (REQ-008 storage.repositories)
        embedder: EmbedderPort 구현체 (REQ-004 ai_agent.adapters.llm.modal_embedding_adapter)

    Returns:
        등록된 노드 수 (현재 53종 — 28 domain + 25 external)

    Notes:
        - 임베딩이 없는 노드는 description 텍스트로 embedder.embed_batch() 일괄 호출
        - 각 노드는 repo.upsert() 호출 — node_id 기준 idempotent
    """
    nodes = discover_node_definitions()
    use_case = RegisterNodesUseCase(repo, embedder)
    return await use_case.execute(nodes)
