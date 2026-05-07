from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UploadPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_size: int
    allowed_types: list[str]
    virus_scan_required: bool = True
