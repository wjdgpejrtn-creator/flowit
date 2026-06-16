"""google_sheets 공용 유틸 unit test — spreadsheet_id 정규화 + 친절 오류 메시지."""
from __future__ import annotations

import pytest

from nodes_graph.adapters.catalog.external._google_sheets_util import (
    extract_spreadsheet_id,
    friendly_sheets_error,
)

_ID = "14Uy8TTECR1XdjeY19jxqoRXFRnEMgBh5"


@pytest.mark.parametrize(
    "raw",
    [
        _ID,  # 이미 순수 ID
        f"https://docs.google.com/spreadsheets/d/{_ID}/edit#gid=1061769880",  # 전체 URL
        f"https://docs.google.com/spreadsheets/d/{_ID}/edit?usp=sharing",  # URL + query
        f"{_ID}/edit#gid=1061769880",  # /d/ 없는 꼬리 붙여넣기
        f"  {_ID}  ",  # 공백 패딩
        f"{_ID}/edit",
    ],
)
def test_extract_spreadsheet_id_variants(raw):
    assert extract_spreadsheet_id(raw) == _ID


def test_extract_spreadsheet_id_empty():
    assert extract_spreadsheet_id("") == ""
    assert extract_spreadsheet_id("   ") == ""


def test_friendly_error_office_file():
    body = (
        '{"error": {"code": 400, "message": "This operation is not supported for this '
        'document. The document must not be an Office file."}}'
    )
    msg = friendly_sheets_error("google_sheets_read", 400, body)
    assert "Office 파일" in msg
    assert "Google Sheets로 저장" in msg


def test_friendly_error_generic_passthrough():
    msg = friendly_sheets_error("google_sheets_read", 404, "Requested entity was not found.")
    assert "404" in msg
    assert "Requested entity was not found" in msg
