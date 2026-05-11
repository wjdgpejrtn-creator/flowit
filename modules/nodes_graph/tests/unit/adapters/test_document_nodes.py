"""Document 카테고리 외부 노드 4종 unit test.

5/13 plan §4.2 박아름 산출물: Drive/Sheets/Docs/OneDrive 4종 NodeDefinition + BaseNode.
process()는 Sprint 3 v1에서 NotImplementedError stub.
"""
from __future__ import annotations

import pytest
from common_schemas.enums import RiskLevel

from nodes_graph.adapters.catalog.external.google_docs_write import (
    GoogleDocsWriteInput,
    GoogleDocsWriteNode,
    get_node_definition as docs_write_def,
)
from nodes_graph.adapters.catalog.external.google_drive_read import (
    GoogleDriveReadInput,
    GoogleDriveReadNode,
    get_node_definition as drive_read_def,
)
from nodes_graph.adapters.catalog.external.google_sheets_read import (
    GoogleSheetsReadInput,
    GoogleSheetsReadNode,
    get_node_definition as sheets_read_def,
)
from nodes_graph.adapters.catalog.external.onedrive_read import (
    OneDriveReadInput,
    OneDriveReadNode,
    get_node_definition as onedrive_read_def,
)


# ----------------------------------------------------------------------
# Google Drive Read
# ----------------------------------------------------------------------


def test_drive_read_definition_fields():
    d = drive_read_def()
    assert d.node_type == "google_drive_read"
    assert d.category == "데이터 소스"
    assert d.risk_level == RiskLevel.MEDIUM
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_drive_read_process_raises_not_implemented():
    node = GoogleDriveReadNode()
    with pytest.raises(NotImplementedError, match="toolset connector"):
        await node.process(GoogleDriveReadInput(file_id="abc"))


# ----------------------------------------------------------------------
# Google Sheets Read
# ----------------------------------------------------------------------


def test_sheets_read_definition_fields():
    d = sheets_read_def()
    assert d.node_type == "google_sheets_read"
    assert d.category == "데이터 소스"
    assert d.risk_level == RiskLevel.MEDIUM
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_sheets_read_process_raises_not_implemented():
    node = GoogleSheetsReadNode()
    with pytest.raises(NotImplementedError, match="toolset connector"):
        await node.process(GoogleSheetsReadInput(spreadsheet_id="ssid", range_a1="Sheet1!A1:B2"))


# ----------------------------------------------------------------------
# Google Docs Write
# ----------------------------------------------------------------------


def test_docs_write_definition_fields():
    d = docs_write_def()
    assert d.node_type == "google_docs_write"
    assert d.category == "문서 생성"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_docs_write_process_raises_not_implemented():
    node = GoogleDocsWriteNode()
    with pytest.raises(NotImplementedError, match="toolset connector"):
        await node.process(GoogleDocsWriteInput(title="t", content="c"))


# ----------------------------------------------------------------------
# OneDrive Read
# ----------------------------------------------------------------------


def test_onedrive_read_definition_fields():
    d = onedrive_read_def()
    assert d.node_type == "onedrive_read"
    assert d.category == "데이터 소스"
    assert d.risk_level == RiskLevel.MEDIUM
    assert d.required_connections == ["microsoft"]
    assert d.service_type == "microsoft_365"


@pytest.mark.asyncio
async def test_onedrive_read_process_raises_not_implemented():
    node = OneDriveReadNode()
    with pytest.raises(NotImplementedError, match="toolset connector"):
        await node.process(OneDriveReadInput(item_id="abc"))


# ----------------------------------------------------------------------
# Cross-checks
# ----------------------------------------------------------------------


def test_all_document_nodes_have_unique_ids():
    ids = {drive_read_def().node_id, sheets_read_def().node_id, docs_write_def().node_id, onedrive_read_def().node_id}
    assert len(ids) == 4


def test_read_vs_write_risk_levels():
    """읽기 노드는 MEDIUM, 쓰기 노드는 HIGH (설계 노트 §1.2 표준)."""
    assert drive_read_def().risk_level == RiskLevel.MEDIUM
    assert sheets_read_def().risk_level == RiskLevel.MEDIUM
    assert onedrive_read_def().risk_level == RiskLevel.MEDIUM
    assert docs_write_def().risk_level == RiskLevel.HIGH


def test_google_workspace_nodes_share_connection_namespace():
    """Drive/Sheets/Docs/Gmail이 모두 ["google"] 통합 connection 사용."""
    for d in (drive_read_def(), sheets_read_def(), docs_write_def()):
        assert d.required_connections == ["google"]
        assert d.service_type == "google_workspace"


def test_microsoft_365_nodes_share_connection_namespace():
    """OneDrive/Outlook/Teams가 모두 ["microsoft"] 통합 connection 사용."""
    assert onedrive_read_def().required_connections == ["microsoft"]
    assert onedrive_read_def().service_type == "microsoft_365"
