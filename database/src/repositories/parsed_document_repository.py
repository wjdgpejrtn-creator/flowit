from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from src.models.document import DocumentBlockModel, DocumentModel
from src.repositories.base import BaseRepository


class ParsedDocumentRepository(BaseRepository[DocumentModel]):
    async def upsert(self, **kwargs) -> DocumentModel:
        doc_id = kwargs.get("id")
        if doc_id:
            existing = await self.get(doc_id)
            if existing:
                for key, value in kwargs.items():
                    if key != "id":
                        setattr(existing, key, value)
                await self.session.flush()
                await self.session.refresh(existing)
                return existing
        return await self.create(**kwargs)

    async def list_by_workflow(
        self, workflow_id: uuid.UUID
    ) -> Sequence[DocumentModel]:
        stmt = select(self.model).where(self.model.workflow_id == workflow_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()
