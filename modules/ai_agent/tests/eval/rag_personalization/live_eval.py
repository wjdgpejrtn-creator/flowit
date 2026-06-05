"""실적용(라이브) RAG 검증 — 실제 GCS + 실제 Modal BGE-M3 end-to-end (§8, Part II).

오프라인 골든(§1~7)이 InMemoryStore+SnapshotEmbedder로 검색 품질만 결정론적으로 쟀다면,
이 러너는 운영과 동일한 GCSMemoryStore + ModalEmbeddingAdapter로:
    seed  : corpus 6종을 GCS에 .md(save_file) + .emb.json(save_embedding)으로 실제 적재
    recall: 라이브 recall(GCS load + Modal embed)로 7시나리오 검색
    diag  : 코사인 분포/마진 + latency 측정 → 오프라인 수치와 대조

대상은 전용 eval user_id(아래 EVAL_USER_ID, 고정 uuid5)라 실유저 데이터와 격리된다.

실행 (repo 루트):
    $env:GOOGLE_APPLICATION_CREDENTIALS = "<GCS SA JSON 로컬 경로>"
    $env:GCS_PERSONAL_BUCKET = "<personal-memory 버킷명>"          # 예: ...-personal-memory-staging
    $env:EMBEDDING_BASE_URL = "<llm-base Modal BGE-M3 엔드포인트>"  # /v1/embed 제공
    $env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONPATH = "modules;packages/common_schemas/python"
    python -m ai_agent.tests.eval.rag_personalization.live_eval [all|seed|recall|cleanup]

all/seed/recall은 자동 정리하지 않는다(검사 후 수동 정리가 의도된 설계). 동일 EVAL_USER_ID라
재실행 시 덮어써져 누적 폭증은 없지만, 끝나면 `cleanup`으로 staging 버킷을 비워두길 권장.
"""
from __future__ import annotations

import asyncio
import sys
import time
import uuid

from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
from ai_agent.adapters.memory.gcs_memory_store import GCSMemoryStore
from ai_agent.application.agents.personalization.recall_personal_skills_use_case import (
    _DEFAULT_MIN_SCORE,
    _DEFAULT_TOP_K,
)
from ai_agent.domain.entities.memory_file import MemoryFileRef

from .corpus import PERSONA_CORPUS
from .harness import aggregate, format_report, run_scenarios
from .scenarios import SCENARIOS, build_query

# 전용 eval user_id (고정 — 실유저 prefix와 충돌 없음, cleanup으로 통째 삭제 가능)
EVAL_USER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "rag-eval.gawon.personalization")

# 운영 기본값을 단일 출처(RecallPersonalSkillsUseCase)에서 그대로 가져온다.
# 이 eval의 목적이 "운영 기본 top_k/min_score의 라이브 타당성 확인"이므로
# 운영값이 바뀌면 eval도 자동으로 따라가야 drift("타당성 확인" misleading)를 막는다.
TOP_K = _DEFAULT_TOP_K
MIN_SCORE = _DEFAULT_MIN_SCORE


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


async def seed(store: GCSMemoryStore, embedder: ModalEmbeddingAdapter) -> list[MemoryFileRef]:
    print(f"\n── SEED → users/{EVAL_USER_ID}/ ──")
    refs: list[MemoryFileRef] = []
    for f in PERSONA_CORPUS:
        await store.save_file(EVAL_USER_ID, f)
        emb = await embedder.embed(f.body)
        await store.save_embedding(EVAL_USER_ID, f.name, emb)
        refs.append(MemoryFileRef(filename=f.filename, name=f.name, description=f.description))
        print(f"  + {f.filename}  (.md + .emb.json[{len(emb)}d])")
    await store.save_index(EVAL_USER_ID, refs)
    print(f"  + MEMORY.md ({len(refs)} refs)")
    return refs


async def diag(store: GCSMemoryStore, embedder: ModalEmbeddingAdapter) -> None:
    """코사인 분포/마진 (오프라인 §3-4 대조용) — GCS에 저장된 임베딩을 그대로 읽어 쓴다."""
    print("\n── DIAG: 코사인 분포 / 마진 ──")
    corpus_emb = {f.name: await store.load_embedding(EVAL_USER_ID, f.name) for f in PERSONA_CORPUS}
    primary_scores: list[float] = []
    distractor_max = 0.0
    for sc in SCENARIOS:
        qv = await embedder.embed(build_query(sc))
        scored = sorted(
            ((_cosine(qv, corpus_emb[n]), n) for n in corpus_emb),
            reverse=True,
        )
        if sc.distractor:
            distractor_max = max(distractor_max, scored[0][0])
            print(f"  [distractor] {sc.utterance!r}  최고={scored[0][0]:.3f}({scored[0][1]})")
        else:
            for p in sc.primary:
                ps = next(s for s, n in scored if n == p)
                primary_scores.append(ps)
            top3 = ", ".join(f"{n}:{s:.3f}" for s, n in scored[:3])
            print(f"  {sc.utterance[:24]:<24} top3=[{top3}]")
    if primary_scores:
        lo, hi = min(primary_scores), max(primary_scores)
        print(f"\n  primary 코사인 min={lo:.3f} max={hi:.3f} avg={sum(primary_scores)/len(primary_scores):.3f}")
        print(f"  distractor 최고={distractor_max:.3f}  →  분리 마진={lo - distractor_max:+.3f}")


async def recall(store: GCSMemoryStore, embedder: ModalEmbeddingAdapter) -> None:
    print(f"\n── RECALL (top_k={TOP_K}, min_score={MIN_SCORE}) ──")
    t0 = time.perf_counter()
    results = await run_scenarios(
        store, embedder, SCENARIOS, top_k=TOP_K, min_score=MIN_SCORE, user_id=EVAL_USER_ID
    )
    dt = time.perf_counter() - t0
    agg = aggregate(results)
    print(format_report(results, agg, top_k=TOP_K, min_score=MIN_SCORE))
    print(f"\n총 recall 시간(7발화, embed 포함): {dt:.2f}s  (평균 {dt/len(SCENARIOS):.2f}s/발화)")
    print("\n── 오프라인 골든(§1~7) 대조 ──")
    print("  골든: hit 100% / 평균노이즈 0.83 / distractor ∅ / 마진 +0.181")


async def cleanup(store: GCSMemoryStore) -> None:
    print(f"\n── CLEANUP users/{EVAL_USER_ID}/ ──")
    # index refs ∪ corpus 합집합으로 삭제 — seed가 save_index 전에 중단돼
    # index가 비어도 corpus 기준으로 orphan .md/.emb.json까지 정리한다.
    # (delete_file은 없는 blob에 대해 no-op이라 중복/누락 없이 안전)
    refs = await store.load_index(EVAL_USER_ID)
    targets = {(r.filename, r.name) for r in refs}
    targets |= {(f.filename, f.name) for f in PERSONA_CORPUS}
    for filename, name in sorted(targets):
        await store.delete_file(EVAL_USER_ID, filename)
        await store.delete_file(EVAL_USER_ID, f"{name}.emb.json")
        print(f"  - {filename} (+ emb)")
    await store.delete_file(EVAL_USER_ID, "MEMORY.md")
    print("  - MEMORY.md")


async def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    store = GCSMemoryStore()
    embedder = ModalEmbeddingAdapter()
    try:
        if cmd in ("all", "seed"):
            await seed(store, embedder)
        if cmd in ("all", "recall"):
            await diag(store, embedder)
            await recall(store, embedder)
        if cmd == "cleanup":
            await cleanup(store)
        elif cmd in ("all", "seed", "recall"):
            # 자동 정리하지 않음(검사 후 수동 정리가 의도) — 끝나면 cleanup 권장.
            print(
                "\n[i] eval blob은 자동 삭제되지 않음 — 정리:"
                " python -m ai_agent.tests.eval.rag_personalization.live_eval cleanup"
            )
    finally:
        await embedder.aclose()


if __name__ == "__main__":
    asyncio.run(main())
