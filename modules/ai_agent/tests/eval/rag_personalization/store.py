"""검증용 인메모리 PersonalMemoryStore.

GCS 대신 dict로 corpus 파일과 임베딩을 들고 있는다. RecallPersonalSkillsUseCase가
요구하는 load_index/load_file/load_embedding 경로만 실제처럼 동작하면 된다.
"""
from __future__ import annotations

from uuid import UUID

from ai_agent.domain.entities.memory_file import MemoryFile, MemoryFileRef
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore


class InMemoryPersonalMemoryStore(PersonalMemoryStore):
    def __init__(
        self,
        files: list[MemoryFile],
        embeddings: dict[str, list[float]] | None = None,
    ) -> None:
        self._by_filename: dict[str, MemoryFile] = {f.filename: f for f in files}
        self._refs: list[MemoryFileRef] = [
            MemoryFileRef(filename=f.filename, name=f.name, description=f.description) for f in files
        ]
        self._embeddings: dict[str, list[float]] = dict(embeddings or {})

    async def load_index(self, user_id: UUID) -> list[MemoryFileRef]:
        return list(self._refs)

    async def save_index(self, user_id: UUID, refs: list[MemoryFileRef]) -> None:
        self._refs = list(refs)

    async def load_file(self, user_id: UUID, filename: str) -> MemoryFile:
        try:
            return self._by_filename[filename]
        except KeyError as exc:
            raise FileNotFoundError(filename) from exc

    async def save_file(self, user_id: UUID, file: MemoryFile) -> None:
        self._by_filename[file.filename] = file

    async def delete_file(self, user_id: UUID, filename: str) -> None:
        self._by_filename.pop(filename, None)

    async def load_embedding(self, user_id: UUID, name: str) -> list[float] | None:
        return self._embeddings.get(name)

    async def save_embedding(self, user_id: UUID, name: str, embedding: list[float]) -> None:
        self._embeddings[name] = embedding
