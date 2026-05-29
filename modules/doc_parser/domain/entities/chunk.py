"""REQ-006 doc_parser — domain/entities/chunk.py

SSOT 이관 (REQ-012, common_schemas 0.11.0): `Chunk`·`ChunkingStrategy`는
common_schemas로 이관됨. 본 파일은 하위호환 shim — 기존 import 경로를 유지하되
신규 코드는 `from common_schemas import ...`를 직접 사용할 것.
"""
from common_schemas import Chunk, ChunkingStrategy

__all__ = ["Chunk", "ChunkingStrategy"]
