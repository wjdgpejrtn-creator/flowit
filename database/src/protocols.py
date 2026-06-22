from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BaseCipher(Protocol):
    """Symmetric encryption interface for credential data (REQ-002 DI)."""

    def encrypt(self, plaintext: bytes) -> bytes: ...

    def decrypt(self, ciphertext: bytes) -> bytes: ...
