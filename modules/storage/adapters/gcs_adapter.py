from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ..domain.ports.object_storage_port import ObjectStoragePort

if TYPE_CHECKING:
    from google.cloud.storage import Bucket


class GCSAdapter(ObjectStoragePort):
    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME", "")
        self._bucket: Bucket | None = None

    def _get_bucket(self) -> Bucket:
        if self._bucket is None:
            from google.cloud import storage

            client = storage.Client()
            self._bucket = client.bucket(self._bucket_name)
        return self._bucket

    async def upload(self, key: str, data: bytes, metadata: dict[str, str]) -> str:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        blob.metadata = metadata
        blob.upload_from_string(data)
        return f"gs://{self._bucket_name}/{key}"

    async def download(self, key: str) -> bytes:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        return blob.download_as_bytes()

    async def delete(self, key: str) -> None:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        blob.delete()

    async def presign(self, key: str, ttl: int = 3600) -> str:
        import datetime

        bucket = self._get_bucket()
        blob = bucket.blob(key)
        return blob.generate_signed_url(expiration=datetime.timedelta(seconds=ttl), method="GET")
