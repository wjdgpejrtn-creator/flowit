"""celery_tasks 단위 테스트 — cancel/resume task의 graceful skip 처리."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from common_schemas.exceptions import ExecutionError
from src.adapters import celery_tasks


def _container(execute_side_effect=None) -> MagicMock:
    """pause_resume_use_case.execute 동작을 제어하는 fake Container."""
    container = MagicMock()
    container.pause_resume_use_case.execute.side_effect = execute_side_effect
    return container


def _patch_container(monkeypatch, container: MagicMock) -> None:
    monkeypatch.setattr(
        "src.dependencies.container.create_container",
        lambda: container,
    )


class TestCancelTask:
    def test_returns_skipped_on_invalid_transition(self, monkeypatch):
        """이미 종료된 execution을 cancel → ExecutionError를 graceful skip으로 변환."""
        exc = ExecutionError(
            "Cannot transition from completed to cancelled",
            code="E_INVALID_STATE_TRANSITION",
        )
        _patch_container(monkeypatch, _container(execute_side_effect=exc))
        execution_id = str(uuid4())

        result = celery_tasks.cancel_execution_task.run(execution_id)

        assert result["status"] == "skipped"
        assert result["action"] == "cancel"
        assert result["execution_id"] == execution_id
        assert "Cannot transition" in result["reason"]

    def test_returns_cancelled_on_success(self, monkeypatch):
        _patch_container(monkeypatch, _container())
        execution_id = str(uuid4())

        result = celery_tasks.cancel_execution_task.run(execution_id)

        assert result["status"] == "cancelled"
        assert result["action"] == "cancel"

    def test_non_execution_error_still_propagates(self, monkeypatch):
        """시스템 장애(ExecutionError 외)는 swallow하지 않고 task 실패로 올린다."""
        _patch_container(monkeypatch, _container(execute_side_effect=RuntimeError("broker down")))

        with pytest.raises(RuntimeError, match="broker down"):
            celery_tasks.cancel_execution_task.run(str(uuid4()))


class TestResumeTask:
    def test_returns_skipped_on_invalid_transition(self, monkeypatch):
        exc = ExecutionError(
            "Cannot transition from completed to running",
            code="E_INVALID_STATE_TRANSITION",
        )
        _patch_container(monkeypatch, _container(execute_side_effect=exc))
        execution_id = str(uuid4())

        result = celery_tasks.resume_execution_task.run(execution_id)

        assert result["status"] == "skipped"
        assert result["action"] == "resume"
        assert result["execution_id"] == execution_id
        assert "Cannot transition" in result["reason"]

    def test_returns_running_on_success(self, monkeypatch):
        _patch_container(monkeypatch, _container())
        execution_id = str(uuid4())

        result = celery_tasks.resume_execution_task.run(execution_id)

        assert result["status"] == "running"
        assert result["action"] == "resume"

    def test_non_execution_error_still_propagates(self, monkeypatch):
        _patch_container(monkeypatch, _container(execute_side_effect=RuntimeError("broker down")))

        with pytest.raises(RuntimeError, match="broker down"):
            celery_tasks.resume_execution_task.run(str(uuid4()))
