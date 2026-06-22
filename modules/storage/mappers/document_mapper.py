from __future__ import annotations

from common_schemas import ContentBlock, DocumentBlock, FileMeta
from common_schemas.document import ParseCoverage, ParserMeta

from ..orm.document_model import DocumentModel


class DocumentMapper:
    @staticmethod
    def to_domain(orm: DocumentModel) -> DocumentBlock:
        return DocumentBlock(
            document_id=orm.document_id,
            workflow_id=orm.workflow_id,
            user_id=orm.user_id,
            file_meta=FileMeta.model_validate(orm.file_meta),
            parser=ParserMeta.model_validate(orm.parser_meta) if orm.parser_meta else None,
            blocks=[ContentBlock.model_validate(b) for b in orm.blocks],
            analysis_status=orm.analysis_status,
            analysis_error=orm.analysis_error,
            analyzed_at=orm.analyzed_at,
            coverage=ParseCoverage.model_validate(orm.coverage) if orm.coverage else None,
        )

    @staticmethod
    def to_orm(entity: DocumentBlock) -> DocumentModel:
        # AnalysisStatus는 str-derived Enum이지만 Python 3.11+ 에서 str(enum)이 repr를
        # 반환하므로 PG ENUM 컬럼 바인딩 시 .value 명시 추출이 안전 (asyncpg 호환).
        return DocumentModel(
            document_id=entity.document_id,
            workflow_id=entity.workflow_id,
            user_id=entity.user_id,
            file_meta=entity.file_meta.model_dump(mode="json"),
            parser_meta=entity.parser.model_dump(mode="json") if entity.parser else None,
            blocks=[b.model_dump(mode="json") for b in entity.blocks],
            analysis_status=entity.analysis_status.value,
            analysis_error=entity.analysis_error,
            analyzed_at=entity.analyzed_at,
            coverage=entity.coverage.model_dump(mode="json") if entity.coverage else None,
        )
