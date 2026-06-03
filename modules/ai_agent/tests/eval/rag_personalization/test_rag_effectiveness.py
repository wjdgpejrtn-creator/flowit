"""RAG 효용성 — 정식 테스트(회귀방지).

두 층:
1. 스모크(HashEmbedder): 스냅샷 없이도 항상 돈다. harness 배선(load_index→embed→
   유사도 정렬→top-k) 이 깨지지 않는지 검증. 의미 검색 정확도는 보지 않는다.
2. 골든 라벨(SnapshotEmbedder): 실제 BGE-M3 스냅샷이 있을 때만 돈다. 발화별 정답
   패턴이 top-k에 드는지 + distractor 게이트 + ON이 OFF보다 노이즈 적은지 assert.

스냅샷은 capture_embeddings.py로 1회 생성(Modal BGE-M3 필요) 후 snapshots/에 커밋한다.
"""
from __future__ import annotations

import pytest

from .corpus import ALL_NAMES, PERSONA_CORPUS
from .embedders import SNAPSHOT_FILE, HashEmbedder, SnapshotEmbedder
from .harness import aggregate, run_scenarios
from .scenarios import SCENARIOS
from .store import InMemoryPersonalMemoryStore

pytestmark = pytest.mark.asyncio

_HAS_SNAPSHOT = SNAPSHOT_FILE.exists()
_requires_snapshot = pytest.mark.skipif(
    not _HAS_SNAPSHOT,
    reason="BGE-M3 골든 스냅샷 미생성 — capture_embeddings.py 실행 필요 (Modal 임베더)",
)


# ── 1. 스모크 (항상 실행) ────────────────────────────────────────────────────
class TestHarnessWiring:
    async def test_off_dumps_full_corpus(self):
        store = InMemoryPersonalMemoryStore(PERSONA_CORPUS)
        results = await run_scenarios(store, HashEmbedder(), SCENARIOS, top_k=3, min_score=0.5)
        # OFF(전체 덤프)는 쿼리와 무관하게 corpus 전부를 반환해야 한다
        for r in results:
            assert set(r.off_returned) == set(ALL_NAMES)

    async def test_recall_path_runs_and_returns_subset(self):
        store = InMemoryPersonalMemoryStore(PERSONA_CORPUS)
        # min_score 낮추고 top_k 키워 recall 정렬 경로 전체를 태운다(의미 무관)
        results = await run_scenarios(store, HashEmbedder(), SCENARIOS, top_k=6, min_score=-1.0)
        for r in results:
            assert set(r.on_returned).issubset(ALL_NAMES)
            assert len(r.on_returned) <= 6


# ── 2. 골든 라벨 (스냅샷 있을 때만) ──────────────────────────────────────────
@_requires_snapshot
class TestRagEffectiveness:
    @pytest.fixture
    def store(self) -> InMemoryPersonalMemoryStore:
        emb = SnapshotEmbedder.from_snapshot()
        # corpus 임베딩도 스냅샷에서 미리 채워 넣는다(on-the-fly 생성 회피)
        seeded = {name: emb.vectors[name] for name in ALL_NAMES if name in emb.vectors}
        return InMemoryPersonalMemoryStore(PERSONA_CORPUS, embeddings=seeded)

    @pytest.mark.parametrize("scenario", [s for s in SCENARIOS if not s.distractor], ids=lambda s: s.utterance)
    async def test_primary_pattern_in_top_k(self, store, scenario):
        results = await run_scenarios(store, SnapshotEmbedder.from_snapshot(), [scenario], top_k=3, min_score=0.5)
        got, want = results[0].on_returned, set(scenario.primary)
        assert results[0].on_hit, f"{scenario.utterance!r} → {got} (기대 primary {want})"

    async def test_distractor_gated_to_empty(self, store):
        distractors = [s for s in SCENARIOS if s.distractor]
        results = await run_scenarios(store, SnapshotEmbedder.from_snapshot(), distractors, top_k=3, min_score=0.5)
        for r in results:
            assert r.on_returned == [], f"distractor가 빈손이 아님: {r.on_returned}"

    async def test_rag_reduces_noise_vs_full_dump(self, store):
        results = await run_scenarios(store, SnapshotEmbedder.from_snapshot(), SCENARIOS, top_k=3, min_score=0.5)
        agg = aggregate(results)
        assert agg.on_avg_noise < agg.off_avg_noise
        assert agg.on_hit_rate >= 0.8
