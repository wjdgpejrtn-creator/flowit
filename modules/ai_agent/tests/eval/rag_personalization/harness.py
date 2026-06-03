"""RAG ON/OFF 비교 harness + 메트릭.

- ON  : RecallPersonalSkillsUseCase (BGE-M3 유사도 top-k, min_score 게이트)
- OFF : load_memory 전체 덤프 — 쿼리와 무관하게 corpus 전부를 주입 (기존 동작)

각 발화에 대해 "정답 패턴이 떴는가(hit)" + "관련없는 패턴이 몇 개 섞였는가(noise)"를
양쪽에서 재서, RAG가 정확도를 올리고 노이즈를 줄이는지 비교한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from nodes_graph.domain.ports.embedder_port import EmbedderPort

from ai_agent.application.agents.personalization.recall_personal_skills_use_case import (
    RecallPersonalSkillsUseCase,
)
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore

from .corpus import ALL_NAMES
from .scenarios import Scenario, build_query


@dataclass(frozen=True)
class ScenarioResult:
    scenario: Scenario
    on_returned: list[str]
    off_returned: list[str]

    @property
    def on_hit(self) -> bool:
        """primary 패턴이 RAG-on 결과 top-k에 모두 들었는가."""
        return self.scenario.primary.issubset(set(self.on_returned))

    @property
    def off_hit(self) -> bool:
        return self.scenario.primary.issubset(set(self.off_returned))

    @property
    def on_noise(self) -> int:
        """gold가 아닌데 반환된 패턴 수 (적을수록 프롬프트 오염 적음)."""
        return len([n for n in self.on_returned if n not in self.scenario.gold])

    @property
    def off_noise(self) -> int:
        return len([n for n in self.off_returned if n not in self.scenario.gold])

    @property
    def distractor_ok(self) -> bool:
        """distractor 발화는 RAG-on이 빈손이어야 정답(게이트 동작)."""
        return (not self.scenario.distractor) or (len(self.on_returned) == 0)


async def _run_off(store: PersonalMemoryStore, user_id: UUID) -> list[str]:
    """load_memory 전체 덤프 모사 — 쿼리 무관 corpus 전부."""
    refs = await store.load_index(user_id)
    return [r.name for r in refs]


async def run_scenarios(
    store: PersonalMemoryStore,
    embedder: EmbedderPort,
    scenarios: list[Scenario],
    *,
    top_k: int = 3,
    min_score: float = 0.5,
    user_id: UUID | None = None,
) -> list[ScenarioResult]:
    uid = user_id or uuid4()
    recall = RecallPersonalSkillsUseCase(store, embedder, top_k=top_k, min_score=min_score)
    off_returned = await _run_off(store, uid)

    results: list[ScenarioResult] = []
    for sc in scenarios:
        files = await recall.execute(uid, build_query(sc))
        results.append(
            ScenarioResult(
                scenario=sc,
                on_returned=[f.name for f in files],
                off_returned=list(off_returned),
            )
        )
    return results


@dataclass(frozen=True)
class Aggregate:
    n_task: int
    on_hit_rate: float
    off_hit_rate: float
    on_avg_noise: float
    off_avg_noise: float
    distractor_pass: bool


def aggregate(results: list[ScenarioResult]) -> Aggregate:
    tasks = [r for r in results if not r.scenario.distractor]
    n = len(tasks) or 1
    return Aggregate(
        n_task=len(tasks),
        on_hit_rate=sum(r.on_hit for r in tasks) / n,
        off_hit_rate=sum(r.off_hit for r in tasks) / n,
        on_avg_noise=sum(r.on_noise for r in tasks) / n,
        off_avg_noise=sum(r.off_noise for r in tasks) / n,
        distractor_pass=all(r.distractor_ok for r in results),
    )


def format_report(results: list[ScenarioResult], agg: Aggregate, *, top_k: int, min_score: float) -> str:
    lines = [
        f"RAG 효용성 비교 (top_k={top_k}, min_score={min_score}, corpus={len(ALL_NAMES)}패턴)",
        "",
        f"{'발화':<34}{'ON hit':<8}{'ON noise':<10}{'OFF noise':<10}ON 반환",
        "-" * 90,
    ]
    for r in results:
        tag = "[distractor]" if r.scenario.distractor else ("O" if r.on_hit else "X")
        utt = r.scenario.utterance[:32]
        lines.append(
            f"{utt:<34}{tag:<8}{r.on_noise:<10}{r.off_noise:<10}{','.join(r.on_returned) or '∅'}"
        )
    lines += [
        "-" * 90,
        f"hit율   ON {agg.on_hit_rate:.0%}  vs  OFF {agg.off_hit_rate:.0%}",
        f"평균노이즈 ON {agg.on_avg_noise:.2f}  vs  OFF {agg.off_avg_noise:.2f}",
        f"distractor 게이트: {'통과' if agg.distractor_pass else '실패'}",
    ]
    return "\n".join(lines)
