"""VaultCredentialProvider 단위 테스트 — 자격증명 복호화 위임."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.adapters.vault_credential_provider import VaultCredentialProvider


class TestVaultCredentialProvider:
    def test_delegates_to_credential_store(self):
        mock_store = MagicMock()
        mock_store.decrypt.return_value = {"api_key": "decrypted_value"}
        provider = VaultCredentialProvider(credential_store=mock_store)

        cred_id = uuid4()
        user_id = uuid4()
        result = provider.get_credential(cred_id, user_id)

        mock_store.decrypt.assert_called_once_with(cred_id, user_id)
        assert result == {"api_key": "decrypted_value"}

    def test_propagates_store_error(self):
        mock_store = MagicMock()
        mock_store.decrypt.side_effect = PermissionError("Access denied")
        provider = VaultCredentialProvider(credential_store=mock_store)

        with pytest.raises(PermissionError, match="Access denied"):
            provider.get_credential(uuid4(), uuid4())
