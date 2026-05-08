from __future__ import annotations

from ...domain.ports.object_storage_port import ObjectStoragePort


class DownloadFileUseCase:
    def __init__(self, storage: ObjectStoragePort) -> None:
        self._storage = storage

    async def execute(self, key: str, presigned: bool = False, ttl: int = 3600) -> str | bytes:
        if presigned:
            return await self._storage.presign(key, ttl)
        return await self._storage.download(key)
