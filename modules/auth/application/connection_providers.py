from __future__ import annotations

from dataclasses import dataclass

from .use_cases.start_connection_authorize_use_case import CONNECTION_SCOPES

# 연결 provider 메타 레지스트리 (ADR-0027) — "이 provider를 어떻게 연결하는가"는 auth 책임.
#
# 어떤 provider가 실제로 쓰이는지(노드 required_connections)는 nodes_graph 카탈로그가 SSOT이고,
# 그 둘을 합쳐 "연결 가능 목록"을 만드는 건 Composition Root(api_server)다. 여기서는 provider별
# 표시명 + 연결 모델만 선언한다.
#
# auth_type:
#   - "oauth"             : 동의화면 redirect(연결 버튼). 실제 가능 여부는 CONNECTION_SCOPES 배선에 따름.
#   - "api_key"           : 사용자 API 키 입력(자격증명 페이지에서 관리 — OAuth 흐름 없음).
#   - "connection_string" : DB 접속 문자열(자격증명 페이지에서 관리).


@dataclass(frozen=True)
class ConnectionProvider:
    service: str
    name: str
    auth_type: str


# 카탈로그 required_connections에 등장하는 provider는 전부 여기 메타가 있어야 한다
# (api_server 드리프트 가드가 강제 — 신규 provider 노드 추가 시 메타 누락이면 테스트 실패).
CONNECTION_PROVIDERS: dict[str, ConnectionProvider] = {
    "google": ConnectionProvider("google", "Google Workspace", "oauth"),
    "slack": ConnectionProvider("slack", "Slack", "oauth"),
    "linear": ConnectionProvider("linear", "Linear", "api_key"),
    "anthropic": ConnectionProvider("anthropic", "Anthropic", "api_key"),
    "postgresql": ConnectionProvider("postgresql", "PostgreSQL", "connection_string"),
    "mysql": ConnectionProvider("mysql", "MySQL", "connection_string"),
}


def is_connectable(service: str) -> bool:
    """지금 실제로 연결 가능한가.

    oauth는 CONNECTION_SCOPES에 배선됐을 때만 동의화면을 띄울 수 있다(예: slack은 SlackOAuthClient
    미배선이라 scope 없음 → False). api_key/connection_string은 키 입력이라 상시 가능(True).
    """
    provider = CONNECTION_PROVIDERS.get(service)
    if provider is None:
        return False
    if provider.auth_type == "oauth":
        return service in CONNECTION_SCOPES
    return True
