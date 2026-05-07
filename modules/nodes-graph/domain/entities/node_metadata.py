from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from common_schemas.enums import RiskLevel


@dataclass(frozen=True)
class NodeMetadata:
    """BaseNode 추상 클래스의 메타데이터."""

    node_id: UUID
    name: str
    category: str
    risk_level: RiskLevel
    is_mvp: bool
