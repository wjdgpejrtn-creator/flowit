"""검증용 임베더 2종.

- SnapshotEmbedder: 실제 BGE-M3로 한 번 떠둔 골든 스냅샷(json)을 텍스트→벡터로 재생.
  CI/eval은 이걸 쓴다(결정론적·네트워크 불필요). 스냅샷이 없으면 KeyError.
- HashEmbedder: 텍스트 해시 기반 의사 임베딩. 의미는 없고 harness 배선 스모크용.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

from nodes_graph.domain.ports.embedder_port import EmbedderPort

_DIM = 768
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_FILE = SNAPSHOT_DIR / "bge_m3_embeddings.json"


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


class SnapshotEmbedder(EmbedderPort):
    """골든 스냅샷 재생 임베더. 실제 BGE-M3 벡터를 그대로 돌려준다."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    @property
    def vectors(self) -> dict[str, list[float]]:
        return self._vectors

    @classmethod
    def from_snapshot(cls, path: Path = SNAPSHOT_FILE) -> SnapshotEmbedder:
        data = json.loads(path.read_text(encoding="utf-8"))
        merged: dict[str, list[float]] = {}
        merged.update(data.get("corpus", {}))
        merged.update(data.get("queries", {}))
        return cls(merged)

    async def embed(self, text: str) -> list[float]:
        try:
            return self._vectors[text]
        except KeyError as exc:
            raise KeyError(f"스냅샷에 없는 텍스트(임베딩 미캡처): {text!r}") from exc

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class HashEmbedder(EmbedderPort):
    """결정론적 의사 임베더. 의미 검색이 아니라 harness 배선 검증 전용."""

    async def embed(self, text: str) -> list[float]:
        out: list[float] = []
        counter = 0
        while len(out) < _DIM:
            digest = hashlib.sha256(f"{text}#{counter}".encode()).digest()
            for i in range(0, len(digest), 4):
                out.append(struct.unpack("<I", digest[i : i + 4])[0] / 0xFFFFFFFF)
                if len(out) >= _DIM:
                    break
            counter += 1
        return _normalize(out)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]
