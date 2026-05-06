from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .base_cipher import BaseCipher

_NONCE_SIZE = 12


class AESGCMCipher(BaseCipher):
    def __init__(self, key: bytes | None = None) -> None:
        if key is None:
            raw = os.getenv("ENCRYPTION_KEY", "")
            key = base64.b64decode(raw)
        self._key = key

    def encrypt(self, plaintext: bytes) -> bytes:
        nonce = os.urandom(_NONCE_SIZE)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        nonce = ciphertext[:_NONCE_SIZE]
        data = ciphertext[_NONCE_SIZE:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(nonce, data, None)
