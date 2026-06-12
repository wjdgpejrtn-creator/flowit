from datetime import UTC, datetime, timedelta
from uuid import UUID

from common_schemas import PlaintextCredential
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import AuthorizationError, NotFoundError
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ..entities.oauth_connection import OAuthConnection
from ..ports.cipher_port import CipherPort
from ..ports.credential_repository import CredentialRepository
from ..ports.oauth_client_port import OAuthClientPort
from ..ports.oauth_connection_repository import OAuthConnectionRepository


class CredentialInjectionService:
    """워크플로우 노드 실행용 credential 해결 (ADR-0018 Decision 5·6).

    `credentials` 테이블을 해결 SSOT로 둔다. `credential_kind` 기반 분기:
    - `oauth_token`: `oauth_connections`로 enrich — service ↔ `required_connections`
      검증 후 access_token 복호화.
    - `api_key` 등: `credentials.encrypted_data` 직접 복호화.

    service-match 정책 (조장 결정, 의도적): `required_connections ↔ service` 검증은
    OAuth credential에만 적용한다. OAuth access token은 특정 provider 스코프에 묶여
    있어 provider 불일치(google 토큰을 slack 노드에) 차단이 필요하지만, api_key는
    워크플로우 작성자가 `node.credential_id`로 명시 선택하는 author-scoped 자원이라
    provider 스코핑 대상이 아니다. 두 경로 모두 RESTRICTED 위험도 게이트 + credential
    활성 검증은 동일하게 거친다.
    """

    def __init__(
        self,
        cipher: CipherPort,
        oauth_repo: OAuthConnectionRepository,
        node_def_repo: NodeDefinitionRepository,
        credential_repo: CredentialRepository,
        oauth_clients: dict[str, OAuthClientPort] | None = None,
    ) -> None:
        self._cipher = cipher
        self._oauth_repo = oauth_repo
        self._node_def_repo = node_def_repo
        self._credential_repo = credential_repo
        # #452 ② service별 OAuth client (service-agnostic, 조장 승인). 현재 google만 배선.
        # 미지정/미배선 service는 refresh 불가 — 유효 토큰은 그대로, known-expired는 명확한 에러.
        self._oauth_clients: dict[str, OAuthClientPort] = oauth_clients or {}

    async def inject(self, credential_id: UUID, node_id: UUID) -> PlaintextCredential:
        node_def = await self._node_def_repo.get_by_id(node_id)
        if node_def is None:
            raise NotFoundError(f"NodeDefinition {node_id} not found")

        if node_def.risk_level == RiskLevel.RESTRICTED:
            raise AuthorizationError(f"Node {node_id} requires elevated permission (RESTRICTED)")

        credential = await self._credential_repo.get_by_id(credential_id)
        if credential is None or not credential.is_active:
            raise NotFoundError(f"Credential {credential_id} not found or inactive")

        if credential.credential_kind == "oauth_token":
            plaintext = await self._resolve_oauth(credential_id, node_def)
        else:
            plaintext = self._cipher.decrypt(credential.encrypted_data).decode()

        return PlaintextCredential(
            credential_id=str(credential_id),
            credential_kind="aes_gcm",
            value=plaintext,
        )

    async def _resolve_oauth(self, credential_id: UUID, node_def) -> str:
        """OAuth credential — oauth_connections로 enrich + service 검증 + 만료 시 refresh 후 복호화."""
        conn = await self._oauth_repo.get_by_credential_id(credential_id)
        if conn is None or not conn.is_active:
            raise NotFoundError(
                f"OAuth connection for credential {credential_id} not found or inactive"
            )

        if node_def.required_connections and node_def.service_type:
            if conn.service not in node_def.required_connections:
                raise AuthorizationError(
                    f"Connection service '{conn.service}' does not match "
                    f"required connections {node_def.required_connections}"
                )

        # #452 ② access token이 만료/임박/미상이면 refresh_token으로 선제 갱신. 갱신 성공 시
        # 새 토큰을 주입하고 oauth_connections에 영속화(다음 주입 비용 절감 + expires_at backfill).
        now = datetime.now(UTC)
        if conn.needs_token_refresh(now):
            refreshed = await self._refresh_access_token(conn, now)
            if refreshed is not None:
                return refreshed

        return self._cipher.decrypt(conn.access_token_encrypted).decode()

    async def _refresh_access_token(self, conn: OAuthConnection, now: datetime) -> str | None:
        """refresh_token으로 access token 갱신. 새 평문 토큰 반환, 갱신 불가/best-effort 시 None.

        - service client 미배선:
            · known-expired면 AuthorizationError(E-CRED-002) — 침묵 401보다 명확한 실패.
            · 레거시(expires_at NULL)면 None → 호출부가 현재 토큰으로 best-effort fallback.
        - refresh 호출 실패: 위와 동일 분기(known-expired는 raise, 레거시는 None).
        """
        client = self._oauth_clients.get(conn.service)
        if client is None:
            self._raise_if_definitely_expired(conn, now)
            return None

        # refresh_token은 needs_token_refresh가 None 아님을 보장(없으면 refresh 대상 아님).
        refresh_token = self._cipher.decrypt(conn.refresh_token_encrypted).decode()
        try:
            resp = await client.refresh_access_token(refresh_token)
        except Exception as exc:  # 네트워크/엔드포인트 실패
            self._raise_if_definitely_expired(conn, now, cause=exc)
            return None

        new_access = resp.get("access_token")
        if not new_access:
            # 200인데 access_token 부재(비정상) — refresh 실패와 동일 취급(정책 일관).
            self._raise_if_definitely_expired(conn, now)
            return None
        new_tokens: dict = {"access_token_encrypted": self._cipher.encrypt(new_access.encode())}
        expires_in = resp.get("expires_in")
        if expires_in is not None:
            new_tokens["access_token_expires_at"] = now + timedelta(seconds=int(expires_in))
        await self._oauth_repo.update_tokens(conn.credential_id, new_tokens)
        return new_access

    @staticmethod
    def _raise_if_definitely_expired(
        conn: OAuthConnection, now: datetime, cause: Exception | None = None
    ) -> None:
        """만료시각이 확정적으로 지난 토큰을 갱신 못 하면 E-CRED-002로 hard-fail."""
        if conn.access_token_expires_at is not None and conn.access_token_expires_at <= now:
            raise AuthorizationError(
                f"OAuth access token for service '{conn.service}' is expired and could not be "
                f"refreshed (E-CRED-002)"
            ) from cause
