"""read/write 비대칭 해소 8종 외부 노드 process() unit test (#438 §6.6).

httpx.AsyncClient를 fake로 치환해 검증(get/post/put/patch + 순차 응답).
- Google R/W 5: google_sheets_write / google_calendar_read / google_docs_read /
  google_drive_upload / gmail_read (connection_token = Google OAuth)
- slack_read (Slack Bot 토큰, 200+ok 계약)
- linear_read / linear_update (Linear API key, GraphQL)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx
import pytest
from common_schemas import NodeContext
from common_schemas.exceptions import ExecutionError, ValidationError

from nodes_graph.adapters.catalog.external.gmail_read import GmailReadInput, GmailReadNode
from nodes_graph.adapters.catalog.external.google_calendar_read import (
    GoogleCalendarReadInput,
    GoogleCalendarReadNode,
)
from nodes_graph.adapters.catalog.external.google_docs_read import (
    GoogleDocsReadInput,
    GoogleDocsReadNode,
)
from nodes_graph.adapters.catalog.external.google_drive_upload import (
    GoogleDriveUploadInput,
    GoogleDriveUploadNode,
)
from nodes_graph.adapters.catalog.external.google_sheets_write import (
    GoogleSheetsWriteInput,
    GoogleSheetsWriteNode,
)
from nodes_graph.adapters.catalog.external.linear_read import LinearReadInput, LinearReadNode
from nodes_graph.adapters.catalog.external.linear_update import LinearUpdateInput, LinearUpdateNode
from nodes_graph.adapters.catalog.external.slack_read import SlackReadInput, SlackReadNode

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


def _ctx(token: str) -> NodeContext:
    return NodeContext(execution_id=uuid4(), user_id=uuid4(), connection_token=token)


@dataclass
class _FakeResponse:
    status_code: int = 200
    json_body: Any = field(default_factory=dict)
    text: str = ""

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

        async def put(self, url, **kwargs):
            ctrl.requests.append({"method": "PUT", "url": url, **kwargs})
            return ctrl._next()

        async def patch(self, url, **kwargs):
            ctrl.requests.append({"method": "PATCH", "url": url, **kwargs})
            return ctrl._next()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _FakeClient(**kw))
    return ctrl


# ----------------------------------------------------------------------
# google_sheets_write
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sheets_write_update_uses_put(fake_http):
    fake_http.responses = [_FakeResponse(200, {
        "updatedRange": "Sheet1!A1:B2", "updatedRows": 2, "updatedColumns": 2, "updatedCells": 4,
    })]
    out = await GoogleSheetsWriteNode().process(
        GoogleSheetsWriteInput(spreadsheet_id="ss1", range_a1="Sheet1!A1", values=[[1, 2], [3, 4]]),
        _ctx("ya29.token"),
    )
    assert fake_http.requests[0]["method"] == "PUT"
    assert out.updated_cells == 4
    assert out.updated_range == "Sheet1!A1:B2"


@pytest.mark.asyncio
async def test_sheets_write_append_uses_post_and_unwraps_updates(fake_http):
    fake_http.responses = [_FakeResponse(200, {
        "updates": {"updatedRange": "Sheet1!A3:B3", "updatedRows": 1, "updatedColumns": 2, "updatedCells": 2},
    })]
    out = await GoogleSheetsWriteNode().process(
        GoogleSheetsWriteInput(spreadsheet_id="ss1", range_a1="Sheet1!A1", values=[[5, 6]], mode="append"),
        _ctx("ya29.token"),
    )
    assert fake_http.requests[0]["method"] == "POST"
    assert fake_http.requests[0]["url"].endswith(":append")
    assert out.updated_rows == 1 and out.updated_cells == 2


@pytest.mark.asyncio
async def test_sheets_write_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GoogleSheetsWriteNode().process(
            GoogleSheetsWriteInput(spreadsheet_id="s", range_a1="A1", values=[[1]]), NODE_CTX
        )


@pytest.mark.asyncio
async def test_sheets_write_bad_mode_raises(fake_http):
    with pytest.raises(ValidationError, match="mode"):
        await GoogleSheetsWriteNode().process(
            GoogleSheetsWriteInput(spreadsheet_id="s", range_a1="A1", values=[[1]], mode="delete"),
            _ctx("t"),
        )


@pytest.mark.asyncio
async def test_sheets_write_api_error_raises(fake_http):
    fake_http.responses = [_FakeResponse(403, text='{"error":"denied"}')]
    with pytest.raises(ExecutionError, match="Google Sheets API 오류 403"):
        await GoogleSheetsWriteNode().process(
            GoogleSheetsWriteInput(spreadsheet_id="s", range_a1="A1", values=[[1]]), _ctx("t")
        )


# ----------------------------------------------------------------------
# google_calendar_read
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_read_returns_events(fake_http):
    fake_http.responses = [_FakeResponse(200, {"items": [
        {"id": "e1", "summary": "회의", "start": {"dateTime": "2026-06-10T09:00:00+09:00"},
         "end": {"dateTime": "2026-06-10T10:00:00+09:00"}, "status": "confirmed", "htmlLink": "https://cal/e1"},
        {"id": "e2", "summary": "점심"},
    ]})]
    out = await GoogleCalendarReadNode().process(
        GoogleCalendarReadInput(time_min="2026-06-10T00:00:00Z", query="회의"), _ctx("ya29.token")
    )
    assert out.count == 2
    assert out.events[0]["id"] == "e1" and out.events[0]["summary"] == "회의"
    assert fake_http.requests[0]["params"]["singleEvents"] == "true"
    assert fake_http.requests[0]["params"]["q"] == "회의"


@pytest.mark.asyncio
async def test_calendar_read_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GoogleCalendarReadNode().process(GoogleCalendarReadInput(), NODE_CTX)


@pytest.mark.asyncio
async def test_calendar_read_api_error_raises(fake_http):
    fake_http.responses = [_FakeResponse(401, text="unauth")]
    with pytest.raises(ExecutionError, match="Google Calendar API 오류 401"):
        await GoogleCalendarReadNode().process(GoogleCalendarReadInput(), _ctx("bad"))


# ----------------------------------------------------------------------
# google_docs_read
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_docs_read_extracts_text(fake_http):
    fake_http.responses = [_FakeResponse(200, {
        "documentId": "doc1",
        "title": "보고서",
        "revisionId": "rev9",
        "body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": "첫 줄\n"}}]}},
            {"paragraph": {"elements": [{"textRun": {"content": "둘째 줄\n"}}]}},
            {"sectionBreak": {}},  # paragraph 아닌 요소는 무시
        ]},
    })]
    out = await GoogleDocsReadNode().process(GoogleDocsReadInput(document_id="doc1"), _ctx("ya29.token"))
    assert out.title == "보고서"
    assert out.text == "첫 줄\n둘째 줄\n"
    assert out.revision_id == "rev9"


@pytest.mark.asyncio
async def test_docs_read_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GoogleDocsReadNode().process(GoogleDocsReadInput(document_id="d"), NODE_CTX)


# ----------------------------------------------------------------------
# google_drive_upload
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drive_upload_two_step_meta_then_media(fake_http):
    fake_http.responses = [
        _FakeResponse(200, {"id": "file1"}),  # files.create 메타
        _FakeResponse(200, {"id": "file1", "name": "out.txt", "mimeType": "text/plain",
                            "webViewLink": "https://drive/file1"}),  # media PATCH
    ]
    import base64
    content = base64.b64encode("리포트 본문".encode()).decode()
    out = await GoogleDriveUploadNode().process(
        GoogleDriveUploadInput(name="out.txt", content_base64=content, folder_id="fld1"),
        _ctx("ya29.token"),
    )
    assert fake_http.requests[0]["method"] == "POST"   # 메타 생성
    assert fake_http.requests[0]["json"]["parents"] == ["fld1"]
    assert fake_http.requests[1]["method"] == "PATCH"  # 미디어 업로드
    assert out.file_id == "file1"
    assert out.web_view_link == "https://drive/file1"


@pytest.mark.asyncio
async def test_drive_upload_meta_error_raises_before_media(fake_http):
    # 1차(files.create 메타) 실패 시 ExecutionError + 2차 media PATCH 미진입.
    fake_http.responses = [_FakeResponse(403, text='{"error":"insufficientPermissions"}')]
    with pytest.raises(ExecutionError, match="Google Drive API 오류 403"):
        await GoogleDriveUploadNode().process(
            GoogleDriveUploadInput(name="x", content_base64="eA=="), _ctx("t")
        )
    assert len(fake_http.requests) == 1  # media PATCH 미진입


@pytest.mark.asyncio
async def test_drive_upload_media_error_raises(fake_http):
    # 메타 성공 후 media 업로드(PATCH) 실패는 별도 메시지로 raise.
    fake_http.responses = [
        _FakeResponse(200, {"id": "file1"}),
        _FakeResponse(413, text='{"error":"payloadTooLarge"}'),
    ]
    with pytest.raises(ExecutionError, match="Google Drive 업로드 오류 413"):
        await GoogleDriveUploadNode().process(
            GoogleDriveUploadInput(name="x", content_base64="eA=="), _ctx("t")
        )
    assert len(fake_http.requests) == 2  # 메타 POST + media PATCH 둘 다 시도


@pytest.mark.asyncio
async def test_drive_upload_bad_base64_raises(fake_http):
    with pytest.raises(ValidationError, match="base64"):
        await GoogleDriveUploadNode().process(
            GoogleDriveUploadInput(name="x", content_base64="!!!not-base64!!!"), _ctx("t")
        )


@pytest.mark.asyncio
async def test_drive_upload_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GoogleDriveUploadNode().process(
            GoogleDriveUploadInput(name="x", content_base64="eA=="), NODE_CTX
        )


# ----------------------------------------------------------------------
# slack_read
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_read_returns_messages(fake_http):
    fake_http.responses = [_FakeResponse(200, {
        "ok": True,
        "messages": [
            {"ts": "1.1", "user": "U1", "text": "안녕", "type": "message"},
            {"ts": "1.2", "user": "U2", "text": "반가워", "type": "message"},
        ],
    })]
    out = await SlackReadNode().process(SlackReadInput(channel="C1", limit=10), _ctx("xoxb-t"))
    assert out.ok is True
    assert out.count == 2 and out.messages[0]["text"] == "안녕"
    assert fake_http.requests[0]["params"]["channel"] == "C1"


@pytest.mark.asyncio
async def test_slack_read_ok_false_raises(fake_http):
    # Slack 논리오류는 200+ok:false (slack_post_message 계약 동일) — Google 노드처럼 실패로 노출.
    fake_http.responses = [_FakeResponse(200, {"ok": False, "error": "channel_not_found"})]
    with pytest.raises(ExecutionError, match="channel_not_found"):
        await SlackReadNode().process(SlackReadInput(channel="bad"), _ctx("xoxb-t"))


@pytest.mark.asyncio
async def test_slack_read_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await SlackReadNode().process(SlackReadInput(channel="C1"), NODE_CTX)


# ----------------------------------------------------------------------
# linear_read
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_linear_read_returns_issues(fake_http):
    fake_http.responses = [_FakeResponse(200, {"data": {"issues": {"nodes": [
        {"id": "i1", "identifier": "ENG-1", "title": "버그", "url": "https://lin/ENG-1",
         "priority": 2, "state": {"name": "In Progress"}, "assignee": {"name": "아름"}, "createdAt": "2026-06-01"},
    ]}}})]
    out = await LinearReadNode().process(
        LinearReadInput(team_id="t1", state_name="In Progress"), _ctx("lin_key")
    )
    assert out.count == 1
    assert out.issues[0]["identifier"] == "ENG-1"
    assert out.issues[0]["state"] == "In Progress" and out.issues[0]["assignee"] == "아름"
    # 필터가 GraphQL variables로 전달됨.
    variables = fake_http.requests[0]["json"]["variables"]
    assert variables["filter"]["team"]["id"]["eq"] == "t1"


@pytest.mark.asyncio
async def test_linear_read_graphql_error_raises(fake_http):
    fake_http.responses = [_FakeResponse(200, {"errors": [{"message": "auth"}]})]
    with pytest.raises(ExecutionError, match="GraphQL"):
        await LinearReadNode().process(LinearReadInput(), _ctx("bad"))


@pytest.mark.asyncio
async def test_linear_read_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await LinearReadNode().process(LinearReadInput(), NODE_CTX)


# ----------------------------------------------------------------------
# linear_update
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_linear_update_success(fake_http):
    fake_http.responses = [_FakeResponse(200, {"data": {"issueUpdate": {
        "success": True,
        "issue": {"id": "i1", "identifier": "ENG-1", "url": "https://lin/ENG-1",
                  "title": "수정됨", "state": {"name": "Done"}, "updatedAt": "2026-06-09"},
    }}})]
    out = await LinearUpdateNode().process(
        LinearUpdateInput(issue_id="i1", state_id="st-done", title="수정됨"), _ctx("lin_key")
    )
    assert out.identifier == "ENG-1" and out.state == "Done"
    assert fake_http.requests[0]["json"]["variables"]["input"]["stateId"] == "st-done"


@pytest.mark.asyncio
async def test_linear_update_no_fields_raises(fake_http):
    with pytest.raises(ValidationError, match="수정할 필드"):
        await LinearUpdateNode().process(LinearUpdateInput(issue_id="i1"), _ctx("lin_key"))


@pytest.mark.asyncio
async def test_linear_update_unsuccessful_raises(fake_http):
    fake_http.responses = [_FakeResponse(200, {"data": {"issueUpdate": {"success": False}}})]
    with pytest.raises(ExecutionError, match="실패"):
        await LinearUpdateNode().process(
            LinearUpdateInput(issue_id="i1", title="x"), _ctx("lin_key")
        )


@pytest.mark.asyncio
async def test_linear_update_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await LinearUpdateNode().process(LinearUpdateInput(issue_id="i1", title="x"), NODE_CTX)


# ----------------------------------------------------------------------
# gmail_read
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_read_list_then_metadata(fake_http):
    fake_http.responses = [
        _FakeResponse(200, {"messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}]}),
        _FakeResponse(200, {"id": "m1", "threadId": "t1", "snippet": "안녕하세요",
                            "payload": {"headers": [{"name": "Subject", "value": "제목1"},
                                                    {"name": "From", "value": "boss@x.com"}]}}),
        _FakeResponse(200, {"id": "m2", "threadId": "t2", "snippet": "두번째",
                            "payload": {"headers": [{"name": "Subject", "value": "제목2"}]}}),
    ]
    out = await GmailReadNode().process(
        GmailReadInput(query="is:unread", max_results=2), _ctx("ya29.token")
    )
    assert out.count == 2
    assert out.messages[0]["subject"] == "제목1" and out.messages[0]["from"] == "boss@x.com"
    assert out.messages[0]["snippet"] == "안녕하세요"
    assert out.messages[1]["subject"] == "제목2" and out.messages[1]["from"] == ""
    assert fake_http.requests[0]["params"]["q"] == "is:unread"


@pytest.mark.asyncio
async def test_gmail_read_empty_inbox(fake_http):
    fake_http.responses = [_FakeResponse(200, {})]  # messages 키 없음
    out = await GmailReadNode().process(GmailReadInput(), _ctx("ya29.token"))
    assert out.count == 0 and out.messages == []


@pytest.mark.asyncio
async def test_gmail_read_list_error_raises(fake_http):
    fake_http.responses = [_FakeResponse(403, text="forbidden")]
    with pytest.raises(ExecutionError, match="Gmail API 오류 403"):
        await GmailReadNode().process(GmailReadInput(), _ctx("bad"))


@pytest.mark.asyncio
async def test_gmail_read_missing_credential_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await GmailReadNode().process(GmailReadInput(), NODE_CTX)
