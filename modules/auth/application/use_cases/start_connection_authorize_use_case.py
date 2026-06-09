from __future__ import annotations

from ...domain.ports.oauth_client_port import OAuthClientPort

# connection 전용 서비스 scope (로그인 신원 scope와 분리 — ADR-0027 ②).
# 노드 required_connections를 충족 (read/write 양방향, #438 §6.6 D):
#   - spreadsheets: sheets read+write (google_sheets_read/write)
#   - drive: drive read+upload (google_drive_read/upload)
#   - documents: docs read+write (google_docs_read/write)
#   - calendar.events: 이벤트 read+write (google_calendar_read/create_event)
#   - gmail.send + gmail.readonly: 메일 송신(gmail_send) + 인박스 조회(gmail_read)
# openid·email은 account_id(sub)·display_name(email) 확보용으로 포함.
CONNECTION_SCOPES: dict[str, list[str]] = {
    "google": [
        "openid",
        "email",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
    ],
    # slack은 후속 PR(②: google-only 우선) — SlackOAuthClient 등록 시 추가.
    # slack_read(conversations.history)/slack_post_message는 SlackOAuthClient 배선 시
    # channels:history·groups:history + chat:write scope와 함께 추가 (#438 D 잔여).
}


class StartConnectionAuthorizeUseCase:
    """connection authorize URL 생성 (ADR-0027). state(CSRF)는 라우터가 Redis에 저장한다."""

    def __init__(self, oauth_client: OAuthClientPort) -> None:
        self._oauth_client = oauth_client

    def build_authorization_url(self, service: str, state: str, redirect_uri: str | None = None) -> str:
        scopes = CONNECTION_SCOPES.get(service)
        if scopes is None:
            raise ValueError(f"Unsupported connection service: {service}")
        # redirect_uri = connection callback 경로(라우터가 전달) — 로그인 callback과 분리해야
        # google이 connection callback으로 돌려보낸다(ADR-0027 셀프리뷰 HIGH 수정).
        return self._oauth_client.authorization_url(state, scopes, redirect_uri)
