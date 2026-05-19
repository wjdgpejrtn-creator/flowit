from __future__ import annotations

import json
import logging
from typing import Any, Protocol
from uuid import UUID

from common_schemas.enums import ExecutionStatus

from ..domain.entities.execution_result import NodeResult
from ..domain.ports.event_publisher_port import EventPublisherPort

logger = logging.getLogger(__name__)


class RedisClientProtocol(Protocol):
    def publish(self, channel: str, message: str) -> int: ...


class SSEEventPublisher(EventPublisherPort):

    CHANNEL_PREFIX = "execution"

    def __init__(self, redis_client: RedisClientProtocol) -> None:
        self._redis = redis_client

    def publish_status(self, execution_id: UUID, status: ExecutionStatus) -> None:
        payload = {
            "type": "status_change",
            "execution_id": str(execution_id),
            "status": status.value,
        }
        self._publish(execution_id, payload)

    def publish_node_complete(self, execution_id: UUID, node_result: NodeResult) -> None:
        payload = {
            "type": "node_complete",
            "execution_id": str(execution_id),
            "node_result": node_result.model_dump(mode="json"),
        }
        self._publish(execution_id, payload)

    def _publish(self, execution_id: UUID, payload: dict[str, Any]) -> None:
        channel = f"{self.CHANNEL_PREFIX}:{execution_id}"
        message = json.dumps(payload, ensure_ascii=False)
        self._redis.publish(channel, message)
        logger.debug("Published to %s: %s", channel, payload.get("type"))
