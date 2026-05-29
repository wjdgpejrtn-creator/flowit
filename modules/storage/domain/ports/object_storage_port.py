from __future__ import annotations

from abc import ABC, abstractmethod


class ObjectStoragePort(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, metadata: dict[str, str]) -> str: ...

    @abstractmethod
    async def download(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def presign(self, key: str, ttl: int = 3600) -> str: ...
