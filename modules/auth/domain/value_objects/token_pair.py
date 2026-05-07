from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TokenPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = 3600
