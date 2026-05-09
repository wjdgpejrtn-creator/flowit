from __future__ import annotations

from ..adapters.catalog.external.http_request import get_node_definition as _http_request
from ..adapters.catalog.external.pdf_generate import get_node_definition as _pdf_generate
from ..domain.catalog import get_domain_node_definitions
from ..domain.entities.node_definition import NodeDefinition


def get_all_node_definitions() -> list[NodeDefinition]:
    """카탈로그 전체 30종 NodeDefinition. RegisterNodesUseCase에서 사용."""
    return [
        *get_domain_node_definitions(),
        _http_request(),
        _pdf_generate(),
    ]
