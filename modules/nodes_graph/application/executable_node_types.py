"""실행 가능한 노드 카탈로그 node_type 집합 — **의존성 없는 SSOT 미러**.

`catalog_registry.get_all_node_classes()`는 62종 BaseNode 클래스를 import하므로(httpx/
fpdf2/pymupdf 등 무거운 어댑터 의존) ai_agent Composer처럼 그 의존을 갖지 않는 모듈이
import하면 `ModuleNotFoundError`로 크래시한다(worker skills_marketplace 사고와 동류).

이 모듈은 **문자열 frozenset만** 노출해 어디서든 import-safe하다. Composer retriever가
검색 후보를 실행 가능한 node_type으로 필터(드래프터가 실행 불가 노드를 못 쓰게)하는 데 쓴다.

⚠️ `get_all_node_classes()` 키와 정확히 일치해야 한다 — drift는
`tests/unit/application/test_executable_node_types.py`가 결정적으로 검증한다.
"""
from __future__ import annotations

EXECUTABLE_NODE_TYPES: frozenset[str] = frozenset({
    "anthropic_chat",
    "api_poll_trigger",
    "base64_decode",
    "base64_encode",
    "bigquery_query",
    "csv_build",
    "csv_parse",
    "data_mapping",
    "date_format",
    "delay",
    "email_send",
    "event_trigger",
    "file_read",
    "file_transform",
    "file_watch_trigger",
    "file_write",
    "gemma_chat",
    "gmail_read",
    "gmail_send",
    "google_calendar_create_event",
    "google_calendar_read",
    "google_docs_read",
    "google_docs_write",
    "google_drive_read",
    "google_drive_upload",
    "google_sheets_read",
    "google_sheets_write",
    "graphql",
    "http_request",
    "if_condition",
    "json_extract",
    "json_merge",
    "json_transform",
    "linear_create_issue",
    "linear_read",
    "linear_update",
    "list_filter",
    "list_map",
    "llm_judge",
    "loop_count",
    "loop_list",
    "manual_trigger",
    "merge_branch",
    "mysql_query",
    "number_calc",
    "pdf_generate",
    "postgresql_query",
    "regex_extract",
    "regex_replace",
    "rest_api",
    "retry",
    "schedule_trigger",
    "slack_notify",
    "slack_post_message",
    "slack_read",
    "stop_workflow",
    "string_template",
    "switch_case",
    "text_template",
    "text_transform",
    "webhook",
    "webhook_trigger",
})
