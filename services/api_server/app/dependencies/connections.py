"""connection use case DI providers (ADR-0027).

라우터 inline 생성 대신 provider로 조립 — 기존 `auth.py` use case provider 패턴과 일관.
"""
from __future__ import annotations

from auth.application.use_cases.complete_connection_use_case import CompleteConnectionUseCase
from auth.application.use_cases.list_connections_use_case import ListConnectionsUseCase
from auth.application.use_cases.revoke_connection_use_case import RevokeConnectionUseCase
from auth.application.use_cases.start_connection_authorize_use_case import StartConnectionAuthorizeUseCase
from auth.domain.ports.cipher_port import CipherPort
from auth.domain.ports.credential_repository import CredentialRepository
from auth.domain.ports.oauth_client_port import OAuthClientPort
from auth.domain.ports.oauth_connection_repository import OAuthConnectionRepository
from fastapi import Depends

from .auth import (
    get_cipher,
    get_credential_repository,
    get_google_oauth,
    get_oauth_repository,
    get_slack_oauth,
)


def get_oauth_clients(
    google_oauth: OAuthClientPort = Depends(get_google_oauth),
    slack_oauth: OAuthClientPort = Depends(get_slack_oauth),
) -> dict[str, OAuthClientPort]:
    """service별 OAuthClientPort 레지스트리 — connection 유스케이스가 service로 라우팅한다.

    provider 추가 시 여기 한 곳만 배선(StartConnectionAuthorize·CompleteConnection 공용).
    """
    return {"google": google_oauth, "slack": slack_oauth}


def get_list_connections_use_case(
    oauth_repo: OAuthConnectionRepository = Depends(get_oauth_repository),
) -> ListConnectionsUseCase:
    return ListConnectionsUseCase(oauth_repo)


def get_start_connection_use_case(
    oauth_clients: dict[str, OAuthClientPort] = Depends(get_oauth_clients),
) -> StartConnectionAuthorizeUseCase:
    return StartConnectionAuthorizeUseCase(oauth_clients)


def get_complete_connection_use_case(
    oauth_repo: OAuthConnectionRepository = Depends(get_oauth_repository),
    credential_repo: CredentialRepository = Depends(get_credential_repository),
    cipher: CipherPort = Depends(get_cipher),
    oauth_clients: dict[str, OAuthClientPort] = Depends(get_oauth_clients),
) -> CompleteConnectionUseCase:
    return CompleteConnectionUseCase(oauth_repo, credential_repo, cipher, oauth_clients)


def get_revoke_connection_use_case(
    oauth_repo: OAuthConnectionRepository = Depends(get_oauth_repository),
) -> RevokeConnectionUseCase:
    return RevokeConnectionUseCase(oauth_repo)
