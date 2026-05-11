from __future__ import annotations

from ..adapters.catalog.external.gmail_send import get_node_definition as _gmail_send
from ..adapters.catalog.external.http_request import get_node_definition as _http_request
from ..adapters.catalog.external.outlook_send import get_node_definition as _outlook_send
from ..adapters.catalog.external.pdf_generate import get_node_definition as _pdf_generate
from ..adapters.catalog.external.slack_post_message import get_node_definition as _slack_post_message
from ..adapters.catalog.external.teams_post_message import get_node_definition as _teams_post_message
from ..domain.catalog import get_domain_node_definitions
from ..domain.entities.node_definition import NodeDefinition


def get_all_node_definitions() -> list[NodeDefinition]:
    """카탈로그 전체 NodeDefinition. RegisterNodesUseCase에서 사용.

    구성:
        - domain/catalog/: 28종 (data 14 + control 8 + trigger 6)
        - adapters/catalog/external/: 6종 (http_request, pdf_generate,
          slack_post_message, gmail_send, outlook_send, teams_post_message)
    """
    return [
        *get_domain_node_definitions(),
        _http_request(),
        _pdf_generate(),
        _slack_post_message(),
        _gmail_send(),
        _outlook_send(),
        _teams_post_message(),
    ]
