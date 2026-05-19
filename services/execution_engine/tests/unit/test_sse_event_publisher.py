"""SSEEventPublisher 단위 테스트 — Redis Pub/Sub 이벤트 발행."""
from __future__ import annotations

import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from common_schemas.enums import ExecutionStatus

from src.adapters.sse_event_publisher import SSEEventPublisher
from src.domain.entities.execution_result import NodeResult


@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def publisher(mock_redis):
    return SSEEventPublisher(redis_client=mock_redis)


class TestPublishStatus:
    def test_publishes_to_correct_channel(self, publisher, mock_redis):
        eid = uuid4()
        publisher.publish_status(eid, ExecutionStatus.RUNNING)

        mock_redis.publish.assert_called_once()
        channel = mock_redis.publish.call_args[0][0]
        assert channel == f"execution:{eid}"

    def test_payload_contains_status(self, publisher, mock_redis):
        eid = uuid4()
        publisher.publish_status(eid, ExecutionStatus.COMPLETED)

        message = json.loads(mock_redis.publish.call_args[0][1])
        assert message["type"] == "status_change"
        assert message["execution_id"] == str(eid)
        assert message["status"] == "completed"

    def test_all_statuses(self, publisher, mock_redis):
        eid = uuid4()
        for status in ExecutionStatus:
            publisher.publish_status(eid, status)
            message = json.loads(mock_redis.publish.call_args[0][1])
            assert message["status"] == status.value


class TestPublishNodeComplete:
    def test_publishes_node_result(self, publisher, mock_redis):
        from datetime import datetime, timezone

        eid = uuid4()
        now = datetime.now(timezone.utc)
        node_result = NodeResult(
            node_instance_id=uuid4(),
            status="succeeded",
            output={"key": "val"},
            started_at=now,
            completed_at=now,
            retry_count=0,
        )

        publisher.publish_node_complete(eid, node_result)

        mock_redis.publish.assert_called_once()
        channel = mock_redis.publish.call_args[0][0]
        assert channel == f"execution:{eid}"

        message = json.loads(mock_redis.publish.call_args[0][1])
        assert message["type"] == "node_complete"
        assert message["node_result"]["status"] == "succeeded"
        assert message["node_result"]["output"] == {"key": "val"}
