from __future__ import annotations

import os

from cryptography.fernet import Fernet

from ...domain.ports.cipher_port import CipherPort


class FernetCipher(CipherPort):
    def __init__(self, key: bytes | None = None) -> None:
        if key is None:
            key = os.getenv("FERNET_KEY", "").encode()
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._fernet.decrypt(ciphertext)
