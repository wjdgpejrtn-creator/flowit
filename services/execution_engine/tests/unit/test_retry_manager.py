"""RetryManager 단위 테스트 — 재시도 판정 및 백오프 계산."""
from __future__ import annotations

import pytest

from src.domain.entities.retry_policy import RetryPolicy
from src.domain.services.retry_manager import RetryManager


@pytest.fixture
def manager():
    return RetryManager()


@pytest.fixture
def default_policy():
    return RetryPolicy()


class TestShouldRetry:
    def test_retryable_error_first_attempt(self, manager, default_policy):
        """retryable 에러 + 첫 시도 → 재시도"""
        assert manager.should_retry(TimeoutError("timeout"), default_policy, attempt=0)

    def test_retryable_error_max_attempts_reached(self, manager, default_policy):
        """retryable 에러 + max 도달 → 재시도 안 함"""
        assert not manager.should_retry(TimeoutError("timeout"), default_policy, attempt=3)

    def test_non_retryable_error(self, manager, default_policy):
        """non-retryable 에러 → 재시도 안 함"""
        assert not manager.should_retry(PermissionError("denied"), default_policy, attempt=0)

    def test_connection_error_retryable(self, manager, default_policy):
        """ConnectionError → retryable"""
        assert manager.should_retry(ConnectionError("reset"), default_policy, attempt=1)

    def test_custom_policy_with_custom_errors(self, manager):
        """커스텀 retryable_errors 목록 적용"""
        policy = RetryPolicy(
            max_retries=5,
            backoff_base_seconds=2.0,
            retryable_errors=["ValueError"],
        )
        assert manager.should_retry(ValueError("bad"), policy, attempt=0)
        assert not manager.should_retry(TypeError("type"), policy, attempt=0)


class TestGetBackoffDelay:
    def test_exponential_backoff_sequence(self, manager, default_policy):
        """지수 백오프: 1s → 2s → 4s"""
        assert manager.get_backoff_delay(default_policy, attempt=0) == 1.0
        assert manager.get_backoff_delay(default_policy, attempt=1) == 2.0
        assert manager.get_backoff_delay(default_policy, attempt=2) == 4.0

    def test_custom_base(self, manager):
        """커스텀 base_seconds 적용"""
        policy = RetryPolicy(max_retries=3, backoff_base_seconds=0.5, retryable_errors=[])
        assert manager.get_backoff_delay(policy, attempt=0) == 0.5
        assert manager.get_backoff_delay(policy, attempt=1) == 1.0
        assert manager.get_backoff_delay(policy, attempt=2) == 2.0
