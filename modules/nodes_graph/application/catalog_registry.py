from __future__ import annotations

from ..adapters.catalog.external.anthropic_chat import AnthropicChatNode
from ..adapters.catalog.external.anthropic_chat import get_node_definition as _anthropic_chat
from ..adapters.catalog.external.bigquery_query import BigqueryQueryNode
from ..adapters.catalog.external.bigquery_query import get_node_definition as _bigquery_query
from ..adapters.catalog.external.data_mapping import DataMappingNode
from ..adapters.catalog.external.data_mapping import get_node_definition as _data_mapping
from ..adapters.catalog.external.email_send import EmailSendNode
from ..adapters.catalog.external.email_send import get_node_definition as _email_send
from ..adapters.catalog.external.file_read import FileReadNode
from ..adapters.catalog.external.file_read import get_node_definition as _file_read
from ..adapters.catalog.external.file_transform import FileTransformNode
from ..adapters.catalog.external.file_transform import get_node_definition as _file_transform
from ..adapters.catalog.external.file_write import FileWriteNode
from ..adapters.catalog.external.file_write import get_node_definition as _file_write
from ..adapters.catalog.external.gemma_chat import GemmaChatNode
from ..adapters.catalog.external.gemma_chat import get_node_definition as _gemma_chat

# 신규 external 8 (#438 §6.6 read/write 비대칭 해소)
from ..adapters.catalog.external.gmail_read import GmailReadNode
from ..adapters.catalog.external.gmail_read import get_node_definition as _gmail_read
from ..adapters.catalog.external.gmail_send import GmailSendNode
from ..adapters.catalog.external.gmail_send import get_node_definition as _gmail_send
from ..adapters.catalog.external.google_calendar_create_event import GoogleCalendarCreateEventNode
from ..adapters.catalog.external.google_calendar_create_event import (
    get_node_definition as _google_calendar_create_event,
)
from ..adapters.catalog.external.google_calendar_read import GoogleCalendarReadNode
from ..adapters.catalog.external.google_calendar_read import get_node_definition as _google_calendar_read
from ..adapters.catalog.external.google_docs_read import GoogleDocsReadNode
from ..adapters.catalog.external.google_docs_read import get_node_definition as _google_docs_read
from ..adapters.catalog.external.google_docs_write import GoogleDocsWriteNode
from ..adapters.catalog.external.google_docs_write import get_node_definition as _google_docs_write
from ..adapters.catalog.external.google_drive_read import GoogleDriveReadNode
from ..adapters.catalog.external.google_drive_read import get_node_definition as _google_drive_read
from ..adapters.catalog.external.google_drive_upload import GoogleDriveUploadNode
from ..adapters.catalog.external.google_drive_upload import get_node_definition as _google_drive_upload
from ..adapters.catalog.external.google_sheets_read import GoogleSheetsReadNode
from ..adapters.catalog.external.google_sheets_read import get_node_definition as _google_sheets_read
from ..adapters.catalog.external.google_sheets_write import GoogleSheetsWriteNode
from ..adapters.catalog.external.google_sheets_write import get_node_definition as _google_sheets_write
from ..adapters.catalog.external.graphql import GraphqlNode
from ..adapters.catalog.external.graphql import get_node_definition as _graphql
from ..adapters.catalog.external.http_request import HttpRequestNode
from ..adapters.catalog.external.http_request import get_node_definition as _http_request
from ..adapters.catalog.external.json_transform import JsonTransformNode
from ..adapters.catalog.external.json_transform import get_node_definition as _json_transform
from ..adapters.catalog.external.linear_create_issue import LinearCreateIssueNode
from ..adapters.catalog.external.linear_create_issue import get_node_definition as _linear_create_issue
from ..adapters.catalog.external.linear_read import LinearReadNode
from ..adapters.catalog.external.linear_read import get_node_definition as _linear_read
from ..adapters.catalog.external.linear_update import LinearUpdateNode
from ..adapters.catalog.external.linear_update import get_node_definition as _linear_update
from ..adapters.catalog.external.llm_judge import LlmJudgeNode
from ..adapters.catalog.external.llm_judge import get_node_definition as _llm_judge
from ..adapters.catalog.external.mysql_query import MysqlQueryNode
from ..adapters.catalog.external.mysql_query import get_node_definition as _mysql_query
from ..adapters.catalog.external.pdf_generate import PdfGenerateNode
from ..adapters.catalog.external.pdf_generate import get_node_definition as _pdf_generate
from ..adapters.catalog.external.postgresql_query import PostgresqlQueryNode
from ..adapters.catalog.external.postgresql_query import get_node_definition as _postgresql_query
from ..adapters.catalog.external.rest_api import RestApiNode
from ..adapters.catalog.external.rest_api import get_node_definition as _rest_api
from ..adapters.catalog.external.slack_notify import SlackNotifyNode
from ..adapters.catalog.external.slack_notify import get_node_definition as _slack_notify
from ..adapters.catalog.external.slack_post_message import SlackPostMessageNode
from ..adapters.catalog.external.slack_post_message import get_node_definition as _slack_post_message
from ..adapters.catalog.external.slack_read import SlackReadNode
from ..adapters.catalog.external.slack_read import get_node_definition as _slack_read
from ..adapters.catalog.external.text_template import TextTemplateNode
from ..adapters.catalog.external.text_template import get_node_definition as _text_template
from ..adapters.catalog.external.webhook import WebhookNode
from ..adapters.catalog.external.webhook import get_node_definition as _webhook
from ..domain.catalog import get_domain_node_classes, get_domain_node_definitions
from ..domain.entities.base_node import BaseNode
from ..domain.entities.node_definition import NodeDefinition


def get_all_node_definitions() -> list[NodeDefinition]:
    """카탈로그 전체 NodeDefinition. RegisterNodesUseCase에서 사용.

    카테고리는 DB CHECK 영문 8종(trigger/action/condition/transform/ai/integration/utility/output)
    안에서 지정. Microsoft(Outlook/Teams/OneDrive) / Notion / OpenAI는 데모 후속 개발로 보류.

    구성 (총 62종):
        - domain/catalog/ 28종: data 14 + control 8 + trigger 6
        - adapters/catalog/external/ 34종:
            · 기존 14종 (박아름 1주차 + gemma_chat PR #68):
              http_request(integration), pdf_generate(output),
              slack_post_message·gmail_send(action),
              google_drive_read·google_sheets_read(integration), google_docs_write(output),
              postgresql_query·mysql_query·bigquery_query(integration),
              anthropic_chat·gemma_chat(ai),
              google_calendar_create_event·linear_create_issue(integration)
            · 신규 11종 (REQ-005 toolset 연동, 박아름 toolset 정리 PR):
              rest_api·graphql(integration), webhook·email_send·slack_notify(action),
              text_template·json_transform·data_mapping·file_transform(transform),
              file_read·file_write(utility)
            · 신규 1종 (#438 §6.6 품질 루프 scorer):
              llm_judge(ai) — 콘텐츠+기준→score:number, if_condition gte가 게이트로 소비
            · 신규 8종 (#438 §6.6 read/write 비대칭 해소, 전부 integration):
              google_sheets_write·google_calendar_read·google_docs_read·google_drive_upload·
              gmail_read(google), slack_read(slack), linear_read·linear_update(linear)

    Note: 중복 3종(http_request_tool=external/http_request, conditional=domain/control/if_condition,
    loop=domain/control/loop_list)은 카탈로그에서 제거. 실행 흐름은
    execution_engine.CatalogNodeExecutor가 node_type으로 BaseNode.process()를 직접 호출 (ADR-0018).
    """
    return [
        *get_domain_node_definitions(),
        # 기존 external 14
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
        _gemma_chat(),
        _google_calendar_create_event(),
        _linear_create_issue(),
        # 신규 external 1 (#438 §6.6 품질 루프 scorer)
        _llm_judge(),
        # 신규 external 8 (#438 §6.6 read/write 비대칭 해소)
        _google_sheets_write(),
        _google_calendar_read(),
        _google_docs_read(),
        _google_drive_upload(),
        _gmail_read(),
        _slack_read(),
        _linear_read(),
        _linear_update(),
        # 신규 external 11 (REQ-005 toolset 연동)
        _rest_api(),
        _graphql(),
        _webhook(),
        _email_send(),
        _slack_notify(),
        _text_template(),
        _json_transform(),
        _data_mapping(),
        _file_read(),
        _file_write(),
        _file_transform(),
    ]


def get_all_node_classes() -> dict[str, type[BaseNode]]:
    """카탈로그 전체 62종 node_type → BaseNode 클래스.

    execution_engine.CatalogNodeExecutor가 node_type으로 노드를 조회·실행한다 (ADR-0018).
    domain 28종 + external 34종 = 62종 전부 process() 실구현 — NotImplementedError 스텁 없음.
    (external 34 = 기존 25 + #438 §6.6 llm_judge scorer 1 + read/write 비대칭 8)
    """
    return {
        **get_domain_node_classes(),
        # 기존 external 14
        "http_request": HttpRequestNode,
        "pdf_generate": PdfGenerateNode,
        "slack_post_message": SlackPostMessageNode,
        "gmail_send": GmailSendNode,
        "google_drive_read": GoogleDriveReadNode,
        "google_sheets_read": GoogleSheetsReadNode,
        "google_docs_write": GoogleDocsWriteNode,
        "postgresql_query": PostgresqlQueryNode,
        "mysql_query": MysqlQueryNode,
        "bigquery_query": BigqueryQueryNode,
        "anthropic_chat": AnthropicChatNode,
        "gemma_chat": GemmaChatNode,
        "google_calendar_create_event": GoogleCalendarCreateEventNode,
        "linear_create_issue": LinearCreateIssueNode,
        # 신규 external 1 (#438 §6.6 품질 루프 scorer)
        "llm_judge": LlmJudgeNode,
        # 신규 external 8 (#438 §6.6 read/write 비대칭 해소)
        "google_sheets_write": GoogleSheetsWriteNode,
        "google_calendar_read": GoogleCalendarReadNode,
        "google_docs_read": GoogleDocsReadNode,
        "google_drive_upload": GoogleDriveUploadNode,
        "gmail_read": GmailReadNode,
        "slack_read": SlackReadNode,
        "linear_read": LinearReadNode,
        "linear_update": LinearUpdateNode,
        # 신규 external 11 (REQ-005 toolset 연동)
        "rest_api": RestApiNode,
        "graphql": GraphqlNode,
        "webhook": WebhookNode,
        "email_send": EmailSendNode,
        "slack_notify": SlackNotifyNode,
        "text_template": TextTemplateNode,
        "json_transform": JsonTransformNode,
        "data_mapping": DataMappingNode,
        "file_read": FileReadNode,
        "file_write": FileWriteNode,
        "file_transform": FileTransformNode,
    }
