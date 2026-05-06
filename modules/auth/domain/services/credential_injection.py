from uuid import UUID

from common_schemas import PlaintextCredential
from common_schemas.exceptions import NotFoundError

from ..ports.cipher_port import CipherPort
from ..ports.oauth_repository import OAuthConnectionRepository


class CredentialInjectionService:
    def __init__(self, oauth_repo: OAuthConnectionRepository, cipher: CipherPort) -> None:
        self._oauth_repo = oauth_repo
        self._cipher = cipher

    async def inject(self, credential_id: UUID) -> PlaintextCredential:
        conn = await self._oauth_repo.get_by_credential_id(credential_id)

        if conn.is_revoked:
            raise NotFoundError(f"Credential {credential_id} is revoked", code="E-CRED-001")

        plaintext = self._cipher.decrypt(conn.encrypted_access_token).decode()

        credential = PlaintextCredential(
            credential_id=str(credential_id),
            credential_kind="aes_gcm",
            value=plaintext,
        )
        return credential
