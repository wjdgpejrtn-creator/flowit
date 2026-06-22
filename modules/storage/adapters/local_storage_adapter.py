from __future__ import annotations

import os
from pathlib import Path

from common_schemas.exceptions import NotFoundError

from ..domain.ports.object_storage_port import ObjectStoragePort


class LocalStorageAdapter(ObjectStoragePort):
    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir or os.getenv("LOCAL_STORAGE_DIR", "/tmp/storage"))

    async def upload(self, key: str, data: bytes, metadata: dict[str, str]) -> str:
        path = self._base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

        meta_path = path.with_suffix(path.suffix + ".meta")
        meta_path.write_text(str(metadata), encoding="utf-8")

        return f"file://{path}"

    async def download(self, key: str) -> bytes:
        path = self._base / key
        if not path.exists():
            raise NotFoundError(f"File not found: {key}", code="E-STORAGE-001")
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._base / key
        if path.exists():
            path.unlink()
        meta_path = path.with_suffix(path.suffix + ".meta")
        if meta_path.exists():
            meta_path.unlink()

    async def presign(self, key: str, ttl: int = 3600) -> str:
        return f"file://{self._base / key}"
