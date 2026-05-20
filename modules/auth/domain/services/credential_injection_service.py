from uuid import UUID

from common_schemas import PlaintextCredential
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import AuthorizationError, NotFoundError
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ..ports.cipher_port import CipherPort
from ..ports.credential_repository import CredentialRepository
from ..ports.oauth_connection_repository import OAuthConnectionRepository


class CredentialInjectionService:
    """워크플로우 노드 실행용 credential 해결 (ADR-0018 Decision 5·6).

    `credentials` 테이블을 해결 SSOT로 둔다. `credential_kind` 기반 분기:
    - `oauth_token`: `oauth_connections`로 enrich — service ↔ `required_connections`
      검증 후 access_token 복호화.
    - `api_key` 등: `credentials.encrypted_data` 직접 복호화 (service-match 비적용 —
      `credentials`에 service 컬럼이 없고, 검증은 OAuth 스코핑 전용).
    """

    def __init__(
        self,
        cipher: CipherPort,
        oauth_repo: OAuthConnectionRepository,
        node_def_repo: NodeDefinitionRepository,
        credential_repo: CredentialRepository,
    ) -> None:
        self._cipher = cipher
        self._oauth_repo = oauth_repo
        self._node_def_repo = node_def_repo
        self._credential_repo = credential_repo

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
        """OAuth credential — oauth_connections로 enrich + service 검증 후 복호화."""
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

        return self._cipher.decrypt(conn.access_token_encrypted).decode()
