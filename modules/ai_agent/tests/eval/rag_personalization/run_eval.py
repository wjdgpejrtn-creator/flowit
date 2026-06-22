"""RAG 효용성 비교 리포트 (수동 실행 — 골든 스냅샷 필요).

스냅샷을 재생해 RAG ON vs OFF 비교표를 출력하고, min_score/top_k 스윕으로
권장값을 찾는다. 대원님 공유용 리포트의 본체.

실행:
    python -m ai_agent.tests.eval.rag_personalization.run_eval
"""
from __future__ import annotations

import asyncio

from .corpus import ALL_NAMES, PERSONA_CORPUS
from .embedders import SNAPSHOT_FILE, SnapshotEmbedder
from .harness import aggregate, format_report, run_scenarios
from .scenarios import SCENARIOS
from .store import InMemoryPersonalMemoryStore

_SWEEP_MIN_SCORE = [0.3, 0.4, 0.5, 0.6, 0.7]
_SWEEP_TOP_K = [2, 3, 5]


def _seeded_store(emb: SnapshotEmbedder) -> InMemoryPersonalMemoryStore:
    seeded = {name: emb.vectors[name] for name in ALL_NAMES if name in emb.vectors}
    return InMemoryPersonalMemoryStore(PERSONA_CORPUS, embeddings=seeded)


async def main() -> None:
    if not SNAPSHOT_FILE.exists():
        print(f"스냅샷 없음: {SNAPSHOT_FILE}\n→ capture_embeddings.py를 먼저 실행하세요 (Modal 임베더 필요).")
        return

    emb = SnapshotEmbedder.from_snapshot()

    # 기본값(top_k=3, min_score=0.5) 상세 리포트
    base = await run_scenarios(_seeded_store(emb), emb, SCENARIOS, top_k=3, min_score=0.5)
    print(format_report(base, aggregate(base), top_k=3, min_score=0.5))

    # 스윕 — 권장값 탐색
    print("\n=== min_score / top_k 스윕 ===")
    print(f"{'top_k':<7}{'min_score':<11}{'hit율':<8}{'노이즈':<8}{'distractor':<10}")
    for k in _SWEEP_TOP_K:
        for ms in _SWEEP_MIN_SCORE:
            res = await run_scenarios(_seeded_store(emb), emb, SCENARIOS, top_k=k, min_score=ms)
            agg = aggregate(res)
            gate = "OK" if agg.distractor_pass else "FAIL"
            print(f"{k:<7}{ms:<11}{agg.on_hit_rate:<8.0%}{agg.on_avg_noise:<8.2f}{gate:<10}")


if __name__ == "__main__":
    asyncio.run(main())
