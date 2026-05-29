"""SSOT 검증 — doc_parser 엔티티 shim이 common_schemas 클래스를 그대로 재노출하는지 확인.

REQ-012 이관 (common_schemas 0.11.0): Chunk/ChunkingStrategy/QualityMetrics/
ParseCoverage/QualityGateResult/WarningInfo는 common_schemas SSOT. doc_parser의
domain/entities/*.py는 하위호환 shim — `is` 동일성이 깨지면 이중 정의 회귀다.
"""
from __future__ import annotations

import common_schemas as cs

from doc_parser.domain.entities.chunk import Chunk, ChunkingStrategy
from doc_parser.domain.entities.quality import ParseCoverage, QualityGateResult, QualityMetrics
from doc_parser.domain.entities.warning import WarningInfo


def test_chunk_shim_is_common_schemas_class():
    assert Chunk is cs.Chunk
    assert ChunkingStrategy is cs.ChunkingStrategy


def test_quality_shim_is_common_schemas_class():
    assert QualityMetrics is cs.QualityMetrics
    assert ParseCoverage is cs.ParseCoverage
    assert QualityGateResult is cs.QualityGateResult


def test_warning_shim_is_common_schemas_class():
    assert WarningInfo is cs.WarningInfo


def test_entities_init_reexports_ssot_classes():
    from doc_parser.domain.entities import Chunk as InitChunk
    from doc_parser.domain.entities import QualityGateResult as InitQGR

    assert InitChunk is cs.Chunk
    assert InitQGR is cs.QualityGateResult
