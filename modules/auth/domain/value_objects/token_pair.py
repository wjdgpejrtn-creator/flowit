from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TokenPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
