from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BeforeValidator


def _ensure_utc(v: datetime | str) -> datetime:
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


UtcDatetime = Annotated[datetime, BeforeValidator(_ensure_utc)]
