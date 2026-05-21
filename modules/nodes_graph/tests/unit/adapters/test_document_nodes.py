"""Document 카테고리 외부 노드 unit test.

Sprint 3 1주차 박아름 작업: Google Drive/Sheets/Docs 3종.
Microsoft OneDrive는 데모 후속 개발로 보류 — 5/11 조장 결정.
process()는 NotImplementedError stub.
category: read는 integration, write는 output (DB CHECK 영문 8종 매핑).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from nodes_graph.adapters.catalog.external.google_docs_write import (
    GoogleDocsWriteInput,
    GoogleDocsWriteNode,
)
from nodes_graph.adapters.catalog.external.google_docs_write import (
    get_node_definition as docs_write_def,
)
from nodes_graph.adapters.catalog.external.google_drive_read import (
    GoogleDriveReadInput,
    GoogleDriveReadNode,
)
from nodes_graph.adapters.catalog.external.google_drive_read import (
    get_node_definition as drive_read_def,
)
from nodes_graph.adapters.catalog.external.google_sheets_read import (
    GoogleSheetsReadInput,
    GoogleSheetsReadNode,
)
from nodes_graph.adapters.catalog.external.google_sheets_read import (
    get_node_definition as sheets_read_def,
)

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


# ----------------------------------------------------------------------
# Google Drive Read
# ----------------------------------------------------------------------


def test_drive_read_definition_fields():
    d = drive_read_def()
    assert d.node_type == "google_drive_read"
    assert d.category == "integration"
    assert d.risk_level == RiskLevel.MEDIUM
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_drive_read_process_requires_credential():
    """ADR-0018 Phase 3d 실구현 — credential 없이 ValidationError.
    실행 경로 전체는 test_db_file_google_nodes.py 참조."""
    node = GoogleDriveReadNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(GoogleDriveReadInput(file_id="abc"), NODE_CTX)


# ----------------------------------------------------------------------
# Google Sheets Read
# ----------------------------------------------------------------------


def test_sheets_read_definition_fields():
    d = sheets_read_def()
    assert d.node_type == "google_sheets_read"
    assert d.category == "integration"
    assert d.risk_level == RiskLevel.MEDIUM
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_sheets_read_process_requires_credential():
    """ADR-0018 Phase 3d 실구현 — credential 없이 ValidationError."""
    node = GoogleSheetsReadNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(
            GoogleSheetsReadInput(spreadsheet_id="ssid", range_a1="Sheet1!A1:B2"), NODE_CTX
        )


# ----------------------------------------------------------------------
# Google Docs Write
# ----------------------------------------------------------------------


def test_docs_write_definition_fields():
    d = docs_write_def()
    assert d.node_type == "google_docs_write"
    assert d.category == "output"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_docs_write_process_requires_credential():
    """ADR-0018 Phase 3d 실구현 — credential 없이 ValidationError."""
    node = GoogleDocsWriteNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(GoogleDocsWriteInput(title="t", content="c"), NODE_CTX)


# ----------------------------------------------------------------------
# Cross-checks
# ----------------------------------------------------------------------


def test_all_document_nodes_have_unique_ids():
    ids = {drive_read_def().node_id, sheets_read_def().node_id, docs_write_def().node_id}
    assert len(ids) == 3


def test_read_vs_write_risk_levels():
    """읽기 노드는 MEDIUM, 쓰기 노드는 HIGH (설계 노트 §1.2 표준)."""
    assert drive_read_def().risk_level == RiskLevel.MEDIUM
    assert sheets_read_def().risk_level == RiskLevel.MEDIUM
    assert docs_write_def().risk_level == RiskLevel.HIGH


def test_google_workspace_nodes_share_connection_namespace():
    """Drive/Sheets/Docs/Gmail이 모두 ["google"] 통합 connection 사용."""
    for d in (drive_read_def(), sheets_read_def(), docs_write_def()):
        assert d.required_connections == ["google"]
        assert d.service_type == "google_workspace"
