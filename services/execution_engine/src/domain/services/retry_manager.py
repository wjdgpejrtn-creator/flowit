from __future__ import annotations

from ..entities.retry_policy import RetryPolicy


class RetryManager:
    """노드 실행 재시도 판정 및 지수 백오프 계산."""

    def should_retry(self, error: Exception, policy: RetryPolicy, attempt: int) -> bool:
        if attempt >= policy.max_retries:
            return False
        error_type = type(error).__name__
        return error_type in policy.retryable_errors

    def get_backoff_delay(self, policy: RetryPolicy, attempt: int) -> float:
        """지수 백오프: base * 2^attempt (1s → 2s → 4s)."""
        return policy.backoff_base_seconds * (2 ** attempt)
