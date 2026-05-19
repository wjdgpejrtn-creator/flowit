from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    retryable_errors: list[str] = Field(default_factory=lambda: [
        "TimeoutError",
        "ConnectionError",
        "HTTPError_5xx",
        "RateLimitError",
    ])
