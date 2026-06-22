from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class HybridCryptoHelper:
    """RSA hybrid encryption for agent-to-agent credential relay."""

    @staticmethod
    def re_encrypt_for_agent(plaintext: bytes, agent_public_key_pem: str) -> bytes:
        public_key = serialization.load_pem_public_key(
            agent_public_key_pem.encode()
        )
        ciphertext = public_key.encrypt(
            plaintext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return ciphertext

    @staticmethod
    def verify_agent_signature(
        payload: bytes, signature: bytes, public_key_pem: str
    ) -> bool:
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode()
        )
        try:
            public_key.verify(
                signature,
                payload,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False
