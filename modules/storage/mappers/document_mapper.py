from __future__ import annotations

from common_schemas import ContentBlock, DocumentBlock, FileMeta
from common_schemas.document import ParserMeta

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
        )

    @staticmethod
    def to_orm(entity: DocumentBlock) -> DocumentModel:
        return DocumentModel(
            document_id=entity.document_id,
            workflow_id=entity.workflow_id,
            user_id=entity.user_id,
            file_meta=entity.file_meta.model_dump(mode="json"),
            parser_meta=entity.parser.model_dump(mode="json") if entity.parser else None,
            blocks=[b.model_dump(mode="json") for b in entity.blocks],
        )
