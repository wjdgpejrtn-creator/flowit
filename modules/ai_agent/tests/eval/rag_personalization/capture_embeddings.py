"""골든 임베딩 스냅샷 1회 생성기 (수동 실행 — 실제 BGE-M3 필요).

corpus 본문 + 발화를 실제 Modal BGE-M3로 임베딩해 snapshots/bge_m3_embeddings.json에
저장한다. 이후 eval/CI는 이 스냅샷만 재생하므로 Modal 없이 결정론적으로 돈다.

선행 조건:
    - agent-personalization/llm-base Modal 임베더가 떠 있어야 함 (현재 재배포 대기)
    - 환경변수 EMBEDDING_BASE_URL 설정

실행:
    EMBEDDING_BASE_URL=https://...modal.run python -m ai_agent.tests.eval.rag_personalization.capture_embeddings
    (또는 repo 루트에서 모듈 경로로 직접 실행)
"""
from __future__ import annotations

import asyncio
import json

from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter

from .corpus import PERSONA_CORPUS
from .embedders import SNAPSHOT_FILE
from .scenarios import SCENARIOS, build_query


async def main() -> None:
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    adapter = ModalEmbeddingAdapter()
    try:
        # corpus: name → embed(body)  (recall의 on-the-fly 경로와 동일 단위)
        corpus_texts = [f.body for f in PERSONA_CORPUS]
        corpus_vecs = await adapter.embed_batch(corpus_texts)
        corpus = {f.name: v for f, v in zip(PERSONA_CORPUS, corpus_vecs)}

        # queries: utterance(=build_query) → embed
        query_texts = [build_query(s) for s in SCENARIOS]
        query_vecs = await adapter.embed_batch(query_texts)
        queries = dict(zip(query_texts, query_vecs))
    finally:
        await adapter.aclose()

    SNAPSHOT_FILE.write_text(
        json.dumps({"corpus": corpus, "queries": queries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"스냅샷 저장 완료: {SNAPSHOT_FILE} (corpus {len(corpus)} / queries {len(queries)})")


if __name__ == "__main__":
    asyncio.run(main())
