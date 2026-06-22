from abc import ABC, abstractmethod


class CipherPort(ABC):
    @abstractmethod
    def encrypt(self, plaintext: bytes) -> bytes: ...

    @abstractmethod
    def decrypt(self, ciphertext: bytes) -> bytes: ...
