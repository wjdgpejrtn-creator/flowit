"""골든 스냅샷 결정적 점검기 (네트워크/DB 불필요).

`/rag-personalization-check` 커맨드의 본체. capture_embeddings.py가 떠둔
snapshots/bge_m3_embeddings.json만 읽어, 우리 하베스트가 그대로 유효한지 4가지를
결정론적으로 assert한다. Modal·GCS·DB 어느 것에도 붙지 않는다.

검사 항목:
  1. 스냅샷 로드   — corpus 6 / queries 7 패턴이 전부 캡처돼 있는가
  2. 768차원 assert — 모든 벡터가 정확히 768차원 float 인가 (프로젝트 전역 차원 SSOT)
  3. 코사인 sanity — 정답(primary) 분리대가 살아 있는가
                     (정답 코사인 ≥ 0.50, distractor 최고 < 0.45, min(primary) > max(distractor))
  4. 시드 왕복     — InMemoryPersonalMemoryStore save→load 가 동일 벡터를 돌려주는가

실행:
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
    PYTHONPATH="modules:packages/common_schemas/python" \
    python -m ai_agent.tests.eval.rag_personalization.check_snapshot

종료코드 0 = 전부 통과, 1 = 하나라도 실패(또는 스냅샷 없음).
"""
from __future__ import annotations

import sys
from uuid import uuid4

from ai_agent.application.agents.personalization.recall_personal_skills_use_case import (
    _cosine_similarity,
)

from .corpus import ALL_NAMES, PERSONA_CORPUS
from .embedders import SNAPSHOT_FILE, SnapshotEmbedder
from .scenarios import SCENARIOS, build_query
from .store import InMemoryPersonalMemoryStore

_EXPECTED_DIM = 768

# 마진 분석(2026-06-03)에서 관측한 분리대. 재캡처가 분리대를 깨면 여기서 잡힌다.
#   정답(primary) 코사인 관측: min 0.553 ~ max 0.754
#   distractor 최고 관측      : 0.372
_PRIMARY_MIN = 0.50   # 정답은 게이트 0.5 위
_PRIMARY_MAX = 0.85   # 비정상적으로 높으면(중복/동일 벡터) 의심
_DISTRACTOR_MAX = 0.45  # distractor 최고는 게이트 아래로 머물러야


class _Check:
    """통과/실패를 모아 마지막에 한 번에 보고한다."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.lines: list[str] = []

    def ok(self, label: str, detail: str = "") -> None:
        self.lines.append(f"  [PASS] {label}{f' — {detail}' if detail else ''}")

    def fail(self, label: str, detail: str) -> None:
        self.lines.append(f"  [FAIL] {label} — {detail}")
        self.failures.append(f"{label}: {detail}")


def _check_loaded(emb: SnapshotEmbedder, c: _Check) -> None:
    missing_corpus = [n for n in ALL_NAMES if n not in emb.vectors]
    if missing_corpus:
        c.fail("스냅샷 로드(corpus)", f"미캡처 패턴 {missing_corpus}")
    else:
        c.ok("스냅샷 로드(corpus)", f"{len(ALL_NAMES)}/{len(ALL_NAMES)} 패턴")

    missing_q = [build_query(s) for s in SCENARIOS if build_query(s) not in emb.vectors]
    if missing_q:
        c.fail("스냅샷 로드(queries)", f"미캡처 발화 {missing_q}")
    else:
        c.ok("스냅샷 로드(queries)", f"{len(SCENARIOS)}/{len(SCENARIOS)} 발화")


def _check_dim(emb: SnapshotEmbedder, c: _Check) -> None:
    bad: list[str] = []
    for key, vec in emb.vectors.items():
        if not isinstance(vec, list) or len(vec) != _EXPECTED_DIM or not all(isinstance(x, (int, float)) for x in vec):
            bad.append(f"{key[:24]}…({len(vec) if isinstance(vec, list) else type(vec).__name__})")
    if bad:
        c.fail(f"{_EXPECTED_DIM}차원 assert", f"{len(bad)}건 불일치: {bad[:3]}")
    else:
        c.ok(f"{_EXPECTED_DIM}차원 assert", f"전체 {len(emb.vectors)}개 벡터 = {_EXPECTED_DIM}차원")


def _check_cosine_sanity(emb: SnapshotEmbedder, c: _Check) -> None:
    primary_scores: list[float] = []
    distractor_scores: list[float] = []

    for sc in SCENARIOS:
        q = emb.vectors[build_query(sc)]
        if sc.distractor:
            top = max(_cosine_similarity(q, emb.vectors[n]) for n in ALL_NAMES)
            distractor_scores.append(top)
            continue
        for name in sc.primary:
            primary_scores.append(_cosine_similarity(q, emb.vectors[name]))

    p_min, p_max = min(primary_scores), max(primary_scores)
    d_max = max(distractor_scores) if distractor_scores else 0.0

    if p_min < _PRIMARY_MIN:
        c.fail("코사인 sanity(정답 하한)", f"정답 최저 {p_min:.3f} < {_PRIMARY_MIN} (게이트 아래로 가라앉음)")
    elif p_max > _PRIMARY_MAX:
        c.fail("코사인 sanity(정답 상한)", f"정답 최고 {p_max:.3f} > {_PRIMARY_MAX} (중복/동일 벡터 의심)")
    else:
        c.ok("코사인 sanity(정답대)", f"primary {p_min:.3f}~{p_max:.3f} ⊂ [{_PRIMARY_MIN}, {_PRIMARY_MAX}]")

    if d_max >= _DISTRACTOR_MAX:
        c.fail("코사인 sanity(distractor)", f"distractor 최고 {d_max:.3f} ≥ {_DISTRACTOR_MAX} (게이트 뚫림 위험)")
    else:
        c.ok("코사인 sanity(distractor)", f"최고 {d_max:.3f} < {_DISTRACTOR_MAX}")

    if p_min <= d_max:
        c.fail("코사인 sanity(분리)", f"정답 최저 {p_min:.3f} ≤ distractor 최고 {d_max:.3f} (순위 역전)")
    else:
        c.ok("코사인 sanity(분리)", f"정답 최저 {p_min:.3f} > distractor 최고 {d_max:.3f} (마진 {p_min - d_max:+.3f})")


async def _check_seed_roundtrip(emb: SnapshotEmbedder, c: _Check) -> None:
    seeded = {name: emb.vectors[name] for name in ALL_NAMES}
    store = InMemoryPersonalMemoryStore(PERSONA_CORPUS, embeddings=seeded)
    uid = uuid4()
    mismatched: list[str] = []
    for name in ALL_NAMES:
        loaded = await store.load_embedding(uid, name)
        if loaded != seeded[name]:
            mismatched.append(name)
    # 신규 저장도 왕복 확인
    probe = emb.vectors[next(iter(ALL_NAMES))]
    await store.save_embedding(uid, "__probe__", probe)
    if await store.load_embedding(uid, "__probe__") != probe:
        mismatched.append("__probe__(save)")

    if mismatched:
        c.fail("시드 저장/로드 왕복", f"불일치 {mismatched}")
    else:
        c.ok("시드 저장/로드 왕복", f"{len(ALL_NAMES)}개 시드 + 신규 저장 1건 동일")


async def main() -> int:
    print(f"=== RAG personalization 스냅샷 점검 ===\n스냅샷: {SNAPSHOT_FILE}")
    if not SNAPSHOT_FILE.exists():
        print("\n[FAIL] 스냅샷 없음 — capture_embeddings.py를 먼저 실행하세요 (Modal BGE-M3 필요).")
        return 1

    emb = SnapshotEmbedder.from_snapshot()
    c = _Check()
    _check_loaded(emb, c)
    _check_dim(emb, c)
    _check_cosine_sanity(emb, c)
    await _check_seed_roundtrip(emb, c)

    print("\n".join(c.lines))
    if c.failures:
        print(f"\n=== 실패 {len(c.failures)}건 ===")
        for f in c.failures:
            print(f"  - {f}")
        return 1
    print("\n=== 전부 통과 ✓ (스냅샷 그대로 유효) ===")
    return 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
