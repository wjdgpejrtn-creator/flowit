"""DocumentMapper coverage 매핑 회귀 테스트 (REQ-009 — 파싱 커버리지 노출).

mapper/ORM 리팩터가 coverage를 silent drop하지 못하도록 양방향 + None 경로를 단언한다.
순수 매핑이라 DB 불필요.
"""
import uuid

from common_schemas import DocumentBlock, FileMeta, ParseCoverage
from common_schemas.enums import AnalysisStatus

from storage.mappers.document_mapper import DocumentMapper


def _doc(coverage: ParseCoverage | None) -> DocumentBlock:
    return DocumentBlock(
        document_id=uuid.uuid4(),
        file_meta=FileMeta(
            file_name="x.pdf", file_type="pdf", mime_type="application/pdf", file_size=1
        ),
        blocks=[],
        analysis_status=AnalysisStatus.COMPLETED,
        coverage=coverage,
    )


def test_coverage_round_trip_preserves_fields() -> None:
    cov = ParseCoverage(
        total_pages=3,
        parsed_pages=3,
        text_blocks=50,
        table_blocks=5,
        vision_blocks=1,
        failed_blocks=1,
        warnings=["페이지 일부 누락"],
    )

    orm = DocumentMapper.to_orm(_doc(cov))
    # ORM에는 JSON(dict)으로 직렬화
    assert isinstance(orm.coverage, dict)
    assert orm.coverage["parsed_pages"] == 3
    assert orm.coverage["failed_blocks"] == 1

    back = DocumentMapper.to_domain(orm)
    # 도메인으로 복원 시 ParseCoverage 전 필드 보존
    assert back.coverage is not None
    assert back.coverage.total_pages == 3
    assert back.coverage.parsed_pages == 3
    assert back.coverage.text_blocks == 50
    assert back.coverage.table_blocks == 5
    assert back.coverage.vision_blocks == 1
    assert back.coverage.failed_blocks == 1
    assert back.coverage.warnings == ["페이지 일부 누락"]


def test_coverage_none_round_trip() -> None:
    orm = DocumentMapper.to_orm(_doc(None))
    assert orm.coverage is None
    assert DocumentMapper.to_domain(orm).coverage is None
