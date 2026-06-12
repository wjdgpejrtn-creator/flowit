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
    # slack bot scope (#438 D): chat:write=slack_post_message,
    # channels:history·groups:history=slack_read(conversations.history) public/private 채널.
    "slack": [
        "chat:write",
        "channels:history",
        "groups:history",
    ],
}


class StartConnectionAuthorizeUseCase:
    """connection authorize URL 생성 (ADR-0027). state(CSRF)는 라우터가 Redis에 저장한다.

    service별 OAuthClientPort를 `oauth_clients` dict로 받아 라우팅한다(google/slack).
    scope는 service 무관 CONNECTION_SCOPES가 SSOT, client는 provider별 authorize 흐름만 담당.
    """

    def __init__(self, oauth_clients: dict[str, OAuthClientPort]) -> None:
        self._oauth_clients = oauth_clients

    def build_authorization_url(self, service: str, state: str, redirect_uri: str | None = None) -> str:
        scopes = CONNECTION_SCOPES.get(service)
        if scopes is None:
            raise ValueError(f"Unsupported connection service: {service}")
        client = self._oauth_clients.get(service)
        if client is None:
            raise ValueError(f"No OAuth client wired for service: {service}")
        # redirect_uri = connection callback 경로(라우터가 전달) — 로그인 callback과 분리해야
        # provider가 connection callback으로 돌려보낸다(ADR-0027 셀프리뷰 HIGH 수정).
        return client.authorization_url(state, scopes, redirect_uri)
