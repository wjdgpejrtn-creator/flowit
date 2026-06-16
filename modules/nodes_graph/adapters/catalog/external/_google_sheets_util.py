"""Google Sheets 노드 공용 유틸 — spreadsheet_id 정규화 + 친절한 오류 메시지.

사용자/LLM이 `spreadsheet_id`에 시트 **전체 URL**(`https://docs.google.com/spreadsheets/d/<ID>/edit#gid=..`)
이나 그 꼬리(`<ID>/edit#gid=..`)를 그대로 넣는 실수가 잦다. 노드는 이 값을 API URL에 그대로
끼워 넣으므로 URL이 깨져 404가 난다. read/write 두 노드가 공유하는 정규화 로직을 한곳에 둔다.
"""
from __future__ import annotations

import re

# 시트 URL의 ``/d/<id>/`` 패턴에서 ID 추출(전체 URL·뒷부분 붙여넣기 모두 커버).
_SPREADSHEET_ID_IN_URL = re.compile(r"/d/([a-zA-Z0-9_-]+)")
# 시트 ID 문자 집합(영숫자·-·_). 그 외 문자(`/`, `?`, `#`, 공백)에서 잘라낸다.
_LEADING_ID = re.compile(r"[a-zA-Z0-9_-]+")

# Drive에 업로드된 Office 파일(.xlsx 등)을 Sheets API로 읽으려 할 때 google이 주는 400 시그니처.
_OFFICE_FILE_MARKER = "must not be an Office file"


def extract_spreadsheet_id(raw: str) -> str:
    """``spreadsheet_id`` 입력에서 순수 시트 ID를 뽑아낸다.

    - 전체 URL / ``/d/<id>/edit#gid=..`` 꼬리: ``/d/`` 뒤 ID 추출
    - ``<id>/edit#gid=..`` 처럼 ID로 시작하는 꼬리: 선행 ID 문자열만 취함
    - 이미 순수 ID: 그대로 반환

    정규화 불가(빈 값/매칭 실패) 시 입력을 strip만 해서 반환(노드가 기존처럼 처리/실패하게 둠).
    """
    s = (raw or "").strip()
    if not s:
        return s
    m = _SPREADSHEET_ID_IN_URL.search(s)
    if m:
        return m.group(1)
    m = _LEADING_ID.match(s)
    return m.group(0) if m else s


def friendly_sheets_error(node_type: str, status_code: int, body_text: str) -> str:
    """Sheets API 오류 응답을 사용자 친화 메시지로 변환.

    가장 흔한 함정인 'Office 파일을 시트로 읽으려 함'(400)은 원인·해법을 명시한 한국어로,
    그 외는 기존처럼 status + 본문 일부를 노출한다.
    """
    if _OFFICE_FILE_MARKER in (body_text or ""):
        return (
            "대상 문서가 업로드된 Office 파일(.xlsx 등)이라 Google Sheets API로 읽을 수 없습니다. "
            "Drive에서 파일을 열고 '파일 → Google Sheets로 저장'으로 변환한 뒤, 변환된 시트의 "
            "ID를 사용하세요."
        )
    return f"Google Sheets API 오류 {status_code}: {(body_text or '')[:200]}"
