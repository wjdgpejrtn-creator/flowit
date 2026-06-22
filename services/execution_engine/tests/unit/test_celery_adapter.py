"""CeleryAdapter 단위 테스트 — dispatch, dispatch_chord, 큐 라우팅."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from src.adapters.celery_adapter import (
    EXECUTE_WORKFLOW_TASK_NAME,
    CeleryAdapter,
)


@pytest.fixture
def mock_app():
    app = MagicMock()
    app.send_task.return_value = MagicMock(id="task-123")
    return app


@pytest.fixture
def adapter(mock_app):
    return CeleryAdapter(mock_app)


class TestDispatch:
    def test_dispatch_returns_task_id(self, adapter, mock_app):
        result = adapter.dispatch("execution_engine.execute_node", {"key": "val"})
        assert result == "task-123"
        mock_app.send_task.assert_called_once_with(
            "execution_engine.execute_node", kwargs={"key": "val"}, queue="default"
        )

    def test_dispatch_routes_to_custom_queue(self, adapter, mock_app):
        adapter.dispatch("execution_engine.execute_node", {"__queue__": "llm", "x": 1})
        mock_app.send_task.assert_called_once_with(
            "execution_engine.execute_node", kwargs={"x": 1}, queue="llm"
        )

    def test_dispatch_pops_queue_key(self, adapter, mock_app):
        args = {"__queue__": "external_api", "data": "test"}
        adapter.dispatch("task", args)
        call_kwargs = mock_app.send_task.call_args[1]["kwargs"]
        assert "__queue__" not in call_kwargs


class TestDispatchChord:
    def test_dispatch_chord_creates_chord(self, adapter, mock_app):
        mock_sig = MagicMock()
        mock_app.signature.return_value = mock_sig

        with patch("src.adapters.celery_adapter.chord") as mock_chord, \
             patch("src.adapters.celery_adapter.group") as mock_group:
            mock_chord_result = MagicMock()
            mock_chord_result.return_value = MagicMock(id="chord-456")
            mock_chord.return_value = mock_chord_result

            result = adapter.dispatch_chord(
                tasks=[
                    {"task_name": "task_a", "args": {"x": 1}},
                    {"task_name": "task_b", "args": {"y": 2}},
                ],
                callback="callback_task",
            )

            assert result == "chord-456"
            assert mock_app.signature.call_count == 3  # 2 tasks + 1 callback


class TestDispatchWorkflow:
    def test_dispatch_workflow_sends_correct_task_name(self, adapter, mock_app):
        exec_id, wf_id, user_id = uuid4(), uuid4(), uuid4()

        task_id = adapter.dispatch_workflow(
            execution_id=exec_id,
            workflow_id=wf_id,
            user_id=user_id,
            trigger_type="resume",
            parameters={"foo": "bar"},
        )

        assert task_id == "task-123"
        mock_app.send_task.assert_called_once()
        call = mock_app.send_task.call_args
        assert call.args[0] == EXECUTE_WORKFLOW_TASK_NAME
        args_list = call.kwargs["args"]
        ctx = args_list[1]
        assert args_list[0] == str(wf_id)
        assert ctx["execution_id"] == str(exec_id)
        assert ctx["workflow_id"] == str(wf_id)
        assert ctx["user_id"] == str(user_id)
        assert ctx["trigger_type"] == "resume"
        assert ctx["parameters"] == {"foo": "bar"}
        assert call.kwargs["queue"] == "default"

    def test_dispatch_workflow_handles_null_user(self, adapter, mock_app):
        adapter.dispatch_workflow(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            user_id=None,
            trigger_type="manual",
        )
        ctx = mock_app.send_task.call_args.kwargs["args"][1]
        assert ctx["user_id"] is None
        assert ctx["parameters"] == {}


class TestRevoke:
    def test_revoke_calls_app_control_revoke(self, adapter, mock_app):
        adapter.revoke("celery-task-abc")
        mock_app.control.revoke.assert_called_once_with(
            "celery-task-abc", terminate=True, signal="SIGTERM",
        )

    def test_revoke_without_terminate(self, adapter, mock_app):
        adapter.revoke("celery-task-def", terminate=False)
        mock_app.control.revoke.assert_called_once_with(
            "celery-task-def", terminate=False, signal="SIGTERM",
        )


class TestResolveQueue:
    def test_ai_routes_to_llm(self):
        assert CeleryAdapter.resolve_queue("ai") == "llm"

    def test_external_routes_to_external_api(self):
        assert CeleryAdapter.resolve_queue("external") == "external_api"

    def test_default_routes_to_default(self):
        assert CeleryAdapter.resolve_queue("data_processing") == "default"

    def test_empty_routes_to_default(self):
        assert CeleryAdapter.resolve_queue("") == "default"
