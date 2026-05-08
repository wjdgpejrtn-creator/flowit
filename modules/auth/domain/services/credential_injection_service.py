from uuid import UUID

from common_schemas import PlaintextCredential
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import AuthorizationError, NotFoundError
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ..ports.cipher_port import CipherPort
from ..ports.oauth_connection_repository import OAuthConnectionRepository


class CredentialInjectionService:
    def __init__(
        self,
        cipher: CipherPort,
        oauth_repo: OAuthConnectionRepository,
        node_def_repo: NodeDefinitionRepository,
    ) -> None:
        self._cipher = cipher
        self._oauth_repo = oauth_repo
        self._node_def_repo = node_def_repo

    async def inject(self, credential_id: UUID, node_id: UUID) -> PlaintextCredential:
        node_def = await self._node_def_repo.get_by_id(node_id)
        if node_def is None:
            raise NotFoundError(f"NodeDefinition {node_id} not found")

        if node_def.risk_level == RiskLevel.RESTRICTED:
            raise AuthorizationError(f"Node {node_id} requires elevated permission (RESTRICTED)")

        conn = await self._oauth_repo.get_by_credential_id(credential_id)
        if conn is None or not conn.is_active:
            raise NotFoundError(f"Credential {credential_id} not found or inactive")

        if node_def.required_connections and node_def.service_type:
            if conn.service not in node_def.required_connections:
                raise AuthorizationError(
                    f"Connection service '{conn.service}' does not match "
                    f"required connections {node_def.required_connections}"
                )

        plaintext = self._cipher.decrypt(conn.access_token_encrypted).decode()

        return PlaintextCredential(
            credential_id=str(credential_id),
            credential_kind="aes_gcm",
            value=plaintext,
        )
