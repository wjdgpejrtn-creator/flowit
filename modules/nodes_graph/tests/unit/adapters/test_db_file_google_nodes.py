"""DB 3 + file 3 + Google 5 외부 노드 process() unit test (ADR-0018 Phase 3d).

- file 3: NODE_FILE_BASE_DIR를 tmp로 잡아 실제 샌드박스 FS 동작 검증
- DB 3: asyncpg/aiomysql 드라이버는 fake로, bigquery는 httpx fake로 치환
- Google 5: httpx.AsyncClient를 fake로 치환
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import aiomysql
import asyncpg
import httpx
import pytest
from common_schemas import NodeContext
from common_schemas.exceptions import ExecutionError, ValidationError

from nodes_graph.adapters.catalog.external.bigquery_query import BigqueryQueryInput, BigqueryQueryNode
from nodes_graph.adapters.catalog.external.file_read import FileReadInput, FileReadNode
from nodes_graph.adapters.catalog.external.file_transform import FileTransformInput, FileTransformNode
from nodes_graph.adapters.catalog.external.file_write import FileWriteInput, FileWriteNode
from nodes_graph.adapters.catalog.external.gmail_send import GmailSendInput, GmailSendNode
from nodes_graph.adapters.catalog.external.google_calendar_create_event import (
    GoogleCalendarCreateEventInput,
    GoogleCalendarCreateEventNode,
)
from nodes_graph.adapters.catalog.external.google_docs_write import (
    GoogleDocsWriteInput,
    GoogleDocsWriteNode,
)
from nodes_graph.adapters.catalog.external.google_drive_read import (
    GoogleDriveReadInput,
    GoogleDriveReadNode,
)
from nodes_graph.adapters.catalog.external.google_sheets_read import (
    GoogleSheetsReadInput,
    GoogleSheetsReadNode,
)
from nodes_graph.adapters.catalog.external.mysql_query import MysqlQueryInput, MysqlQueryNode
from nodes_graph.adapters.catalog.external.postgresql_query import (
    PostgresqlQueryInput,
    PostgresqlQueryNode,
)

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


def _ctx(token: str) -> NodeContext:
    return NodeContext(execution_id=uuid4(), user_id=uuid4(), connection_token=token)


# ======================================================================
# file 3 — 실제 샌드박스 FS
# ======================================================================


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("NODE_FILE_BASE_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_file_write_then_read_roundtrip(sandbox):
    await FileWriteNode().process(
        FileWriteInput(path="sub/note.txt", content="안녕 아름", create_parents=True), NODE_CTX
    )
    out = await FileReadNode().process(FileReadInput(path="sub/note.txt"), NODE_CTX)
    assert out.content == "안녕 아름"
    assert out.size_bytes > 0


@pytest.mark.asyncio
async def test_file_read_missing_file_raises(sandbox):
    with pytest.raises(ValidationError, match="찾을 수 없"):
        await FileReadNode().process(FileReadInput(path="nope.txt"), NODE_CTX)


@pytest.mark.asyncio
async def test_file_path_traversal_blocked(sandbox):
    """`..` 탈출은 ValidationError로 차단."""
    with pytest.raises(ValidationError, match="샌드박스"):
        await FileReadNode().process(FileReadInput(path="../../etc/passwd"), NODE_CTX)


@pytest.mark.asyncio
async def test_file_absolute_path_is_contained(sandbox):
    """절대 경로는 차단이 아니라 leading separator 제거로 샌드박스 내부에 contained —
    워커의 실제 /etc 등에는 접근 불가."""
    out = await FileWriteNode().process(
        FileWriteInput(path="/etc/evil", content="x", create_parents=True), NODE_CTX
    )
    assert str(sandbox) in out.path
    assert out.path.replace("\\", "/").endswith("/etc/evil")


@pytest.mark.asyncio
async def test_file_transform_csv_to_json(sandbox):
    await FileWriteNode().process(
        FileWriteInput(path="in.csv", content="name,age\n아름,30\n대원,28\n"), NODE_CTX
    )
    out = await FileTransformNode().process(
        FileTransformInput(
            source_path="in.csv", target_path="out.json",
            source_format="csv", target_format="json",
        ),
        NODE_CTX,
    )
    assert out.rows_processed == 2
    result = await FileReadNode().process(FileReadInput(path="out.json"), NODE_CTX)
    assert "아름" in result.content


# ======================================================================
# DB — postgresql / mysql (driver fake)
# ======================================================================


class _FakePgConn:
    def __init__(self, records: list[dict]) -> None:
        self._records = records

    async def fetch(self, query, *args, timeout=None):
        return self._records

    async def fetchrow(self, query, *args, timeout=None):
        return self._records[0] if self._records else None

    async def execute(self, query, *args, timeout=None):
        return "UPDATE 2"

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_postgresql_query_fetch_all(monkeypatch):
    async def _fake_connect(*a, **kw):
        return _FakePgConn([{"id": 1, "name": "아름"}, {"id": 2, "name": "대원"}])

    monkeypatch.setattr(asyncpg, "connect", _fake_connect)
    out = await PostgresqlQueryNode().process(
        PostgresqlQueryInput(query="SELECT * FROM t"),
        _ctx("postgresql://u:p@93.184.216.34:5432/db"),
    )
    assert out.row_count == 2
    assert out.fields == ["id", "name"]
    assert out.rows[0]["name"] == "아름"


@pytest.mark.asyncio
async def test_postgresql_query_none_mode_row_count(monkeypatch):
    async def _fake_connect(*a, **kw):
        return _FakePgConn([])

    monkeypatch.setattr(asyncpg, "connect", _fake_connect)
    out = await PostgresqlQueryNode().process(
        PostgresqlQueryInput(query="UPDATE t SET x=1", fetch_mode="none"),
        _ctx("postgresql://u:p@93.184.216.34/db"),
    )
    assert out.row_count == 2  # "UPDATE 2"


@pytest.mark.asyncio
async def test_postgresql_query_missing_credential_raises():
    with pytest.raises(ValidationError, match="credential"):
        await PostgresqlQueryNode().process(PostgresqlQueryInput(query="SELECT 1"), NODE_CTX)


class _FakeMyCursor:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.rowcount = len(rows)
        self.description = [("id",), ("name",)]

    async def execute(self, query, args=None):
        pass

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeMyConn:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def cursor(self, cursor_class=None):
        return _FakeMyCursor(self._rows)

    async def commit(self):
        pass

    def close(self):
        pass


@pytest.mark.asyncio
async def test_mysql_query_fetch_all(monkeypatch):
    async def _fake_connect(*a, **kw):
        return _FakeMyConn([{"id": 1, "name": "아름"}])

    monkeypatch.setattr(aiomysql, "connect", _fake_connect)
    out = await MysqlQueryNode().process(
        MysqlQueryInput(query="SELECT * FROM t"),
        _ctx("mysql://u:p@93.184.216.34:3306/db"),
    )
    assert out.row_count == 1
    assert out.fields == ["id", "name"]


@pytest.mark.asyncio
async def test_mysql_query_missing_credential_raises():
    with pytest.raises(ValidationError, match="credential"):
        await MysqlQueryNode().process(MysqlQueryInput(query="SELECT 1"), NODE_CTX)


# ======================================================================
# httpx fake — bigquery + Google 5
# ======================================================================


@dataclass
class _FakeResponse:
    status_code: int = 200
    json_body: Any = field(default_factory=dict)
    text: str = ""
    content: bytes = b""

    def json(self) -> Any:
        return self.json_body


class _HttpController:
    def __init__(self) -> None:
        self.responses: list[_FakeResponse] = [_FakeResponse()]
        self.requests: list[dict] = []
        self._i = 0

    def _next(self) -> _FakeResponse:
        idx = min(self._i, len(self.responses) - 1)
        self._i += 1
        return self.responses[idx]


@pytest.fixture
def fake_http(monkeypatch):
    ctrl = _HttpController()

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def get(self, url, **kwargs):
            ctrl.requests.append({"method": "GET", "url": url, **kwargs})
            return ctrl._next()

        async def post(self, url, **kwargs):
            ctrl.requests.append({"method": "POST", "url": url, **kwargs})
            return ctrl._next()

        async def patch(self, url, **kwargs):
            ctrl.requests.append({"method": "PATCH", "url": url, **kwargs})
            return ctrl._next()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _FakeClient(**kw))
    return ctrl


# ----------------------------------------------------------------------
# bigquery_query
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bigquery_query_success(fake_http):
    fake_http.responses = [_FakeResponse(200, {
        "jobReference": {"jobId": "job-1"},
        "schema": {"fields": [{"name": "id", "type": "INTEGER"}, {"name": "name", "type": "STRING"}]},
        "rows": [{"f": [{"v": "1"}, {"v": "아름"}]}],
        "totalRows": "1",
        "totalBytesProcessed": "2048",
    })]
    out = await BigqueryQueryNode().process(
        BigqueryQueryInput(project_id="proj", query="SELECT 1"), _ctx("ya29.token")
    )
    assert out.job_id == "job-1"
    assert out.rows == [{"id": "1", "name": "아름"}]
    assert out.total_bytes_processed == 2048
    assert out.schema[0] == {"name": "id", "type": "INTEGER"}


@pytest.mark.asyncio
async def test_bigquery_query_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await BigqueryQueryNode().process(
            BigqueryQueryInput(project_id="p", query="SELECT 1"), NODE_CTX
        )


@pytest.mark.asyncio
async def test_bigquery_query_api_error_raises(fake_http):
    fake_http.responses = [_FakeResponse(403, text='{"error": "denied"}')]
    with pytest.raises(ExecutionError, match="BigQuery API 오류 403"):
        await BigqueryQueryNode().process(
            BigqueryQueryInput(project_id="p", query="SELECT 1"), _ctx("token")
        )


# ----------------------------------------------------------------------
# gmail_send
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_send_success(fake_http):
    fake_http.responses = [_FakeResponse(200, {
        "id": "msg-1", "threadId": "thr-1", "labelIds": ["SENT"],
    })]
    out = await GmailSendNode().process(
        GmailSendInput(to=["a@b.com"], subject="제목", body="본문"), _ctx("ya29.token")
    )
    assert out.message_id == "msg-1"
    assert out.label_ids == ["SENT"]
    assert "raw" in fake_http.requests[0]["json"]


@pytest.mark.asyncio
async def test_gmail_send_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GmailSendNode().process(
            GmailSendInput(to=["a@b.com"], subject="s", body="b"), NODE_CTX
        )


# ----------------------------------------------------------------------
# google_calendar_create_event
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_calendar_create_event_success(fake_http):
    fake_http.responses = [_FakeResponse(200, {
        "id": "ev-1", "htmlLink": "https://cal/ev-1",
        "iCalUID": "uid-1", "status": "confirmed", "created": "2026-05-21T00:00:00Z",
    })]
    out = await GoogleCalendarCreateEventNode().process(
        GoogleCalendarCreateEventInput(
            calendar_id="primary", summary="회의",
            start="2026-05-22T09:00:00+09:00", end="2026-05-22T10:00:00+09:00",
        ),
        _ctx("ya29.token"),
    )
    assert out.event_id == "ev-1"
    assert out.status == "confirmed"


@pytest.mark.asyncio
async def test_google_calendar_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GoogleCalendarCreateEventNode().process(
            GoogleCalendarCreateEventInput(
                calendar_id="primary", summary="x", start="s", end="e"
            ),
            NODE_CTX,
        )


# ----------------------------------------------------------------------
# google_docs_write
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_docs_write_create_with_content(fake_http):
    fake_http.responses = [
        _FakeResponse(200, {"documentId": "doc-1", "title": "보고서", "revisionId": "rev-1"}),
        _FakeResponse(200, {"writeControl": {"requiredRevisionId": "rev-2"}}),
    ]
    out = await GoogleDocsWriteNode().process(
        GoogleDocsWriteInput(title="보고서", content="본문 내용"), _ctx("ya29.token")
    )
    assert out.document_id == "doc-1"
    assert out.revision_id == "rev-2"
    assert out.web_link == "https://docs.google.com/document/d/doc-1/edit"
    # 2 calls: documents.create + batchUpdate
    assert len(fake_http.requests) == 2


@pytest.mark.asyncio
async def test_google_docs_write_new_doc_requires_title(fake_http):
    with pytest.raises(ValidationError, match="title"):
        await GoogleDocsWriteNode().process(
            GoogleDocsWriteInput(content="x"), _ctx("token")
        )


@pytest.mark.asyncio
async def test_google_docs_write_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GoogleDocsWriteNode().process(
            GoogleDocsWriteInput(title="t", content="c"), NODE_CTX
        )


# ----------------------------------------------------------------------
# google_drive_read
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_drive_read_as_text(fake_http):
    fake_http.responses = [
        _FakeResponse(200, {"id": "f1", "name": "doc.txt", "mimeType": "text/plain", "size": "9"}),
        _FakeResponse(200, content="안녕 아름".encode()),
    ]
    out = await GoogleDriveReadNode().process(
        GoogleDriveReadInput(file_id="f1", as_text=True), _ctx("ya29.token")
    )
    assert out.name == "doc.txt"
    assert out.text == "안녕 아름"
    assert out.content_base64  # base64 항상 채움


@pytest.mark.asyncio
async def test_google_drive_read_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GoogleDriveReadNode().process(GoogleDriveReadInput(file_id="f1"), NODE_CTX)


# ----------------------------------------------------------------------
# google_sheets_read
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_sheets_read_success(fake_http):
    fake_http.responses = [_FakeResponse(200, {
        "range": "Sheet1!A1:B2", "majorDimension": "ROWS",
        "values": [["이름", "나이"], ["아름", "30"]],
    })]
    out = await GoogleSheetsReadNode().process(
        GoogleSheetsReadInput(spreadsheet_id="sheet-1", range_a1="Sheet1!A1:B2"),
        _ctx("ya29.token"),
    )
    assert out.row_count == 2
    assert out.values[1] == ["아름", "30"]
    assert out.range_resolved == "Sheet1!A1:B2"


@pytest.mark.asyncio
async def test_google_sheets_read_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GoogleSheetsReadNode().process(
            GoogleSheetsReadInput(spreadsheet_id="s", range_a1="A1:B2"), NODE_CTX
        )
