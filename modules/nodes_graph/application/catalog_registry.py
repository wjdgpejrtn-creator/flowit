from __future__ import annotations

from ..adapters.catalog.external.anthropic_chat import get_node_definition as _anthropic_chat
from ..adapters.catalog.external.bigquery_query import get_node_definition as _bigquery_query
from ..adapters.catalog.external.gmail_send import get_node_definition as _gmail_send
from ..adapters.catalog.external.google_calendar_create_event import get_node_definition as _google_calendar_create_event
from ..adapters.catalog.external.google_docs_write import get_node_definition as _google_docs_write
from ..adapters.catalog.external.google_drive_read import get_node_definition as _google_drive_read
from ..adapters.catalog.external.google_sheets_read import get_node_definition as _google_sheets_read
from ..adapters.catalog.external.http_request import get_node_definition as _http_request
from ..adapters.catalog.external.linear_create_issue import get_node_definition as _linear_create_issue
from ..adapters.catalog.external.mysql_query import get_node_definition as _mysql_query
from ..adapters.catalog.external.pdf_generate import get_node_definition as _pdf_generate
from ..adapters.catalog.external.postgresql_query import get_node_definition as _postgresql_query
from ..adapters.catalog.external.slack_post_message import get_node_definition as _slack_post_message
from ..domain.catalog import get_domain_node_definitions
from ..domain.entities.node_definition import NodeDefinition


def get_all_node_definitions() -> list[NodeDefinition]:
    """카탈로그 전체 NodeDefinition. RegisterNodesUseCase에서 사용.

    카테고리는 DB CHECK 영문 8종(trigger/action/condition/transform/ai/integration/utility/output)
    안에서 지정. Microsoft(Outlook/Teams/OneDrive) / Notion / OpenAI는 데모 후속 개발로 보류.

    구성 (총 41종):
        - domain/catalog/: 28종 (data 14 + control 8 + trigger 6)
        - adapters/catalog/external/ 기타 2종: http_request(integration), pdf_generate(output)
        - adapters/catalog/external/ Communication 2종: slack_post_message, gmail_send (action)
        - adapters/catalog/external/ Document 3종: google_drive_read, google_sheets_read (integration), google_docs_write (output)
        - adapters/catalog/external/ Data 3종: postgresql_query, mysql_query, bigquery_query (integration)
        - adapters/catalog/external/ AI/ML 1종: anthropic_chat (ai)
        - adapters/catalog/external/ Productivity 2종: google_calendar_create_event, linear_create_issue (integration)
    """
    return [
        *get_domain_node_definitions(),
        _http_request(),
        _pdf_generate(),
        _slack_post_message(),
        _gmail_send(),
        _google_drive_read(),
        _google_sheets_read(),
        _google_docs_write(),
        _postgresql_query(),
        _mysql_query(),
        _bigquery_query(),
        _anthropic_chat(),
        _google_calendar_create_event(),
        _linear_create_issue(),
    ]
