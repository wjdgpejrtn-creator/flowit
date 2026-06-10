from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.skeleton import SlotRole

# 슬롯→노드 LLM 매핑 포트 (ADR-0026 §6.6 Phase 2 — 앙상블 LLM voter).
#
# 싼 voter(lexical/semantic/ontology)가 확신 못 하는 슬롯만 지연 escalation으로 호출된다
# (EnsembleSlotResolver). Gemma가 발화의 방향성("gmail에서"=읽기 source vs "gmail로"=보내기
# sink)을 후보 풀 안에서 디스앰비규에이션. 구현체는 ai_agent/adapters/llm (LLMPort 위, ADR-0013
# Modal 호출 어댑터=호출 모듈 보유). composition root가 주입하고, 미주입이면 앙상블은 싼
# voter만으로 동작(graceful degrade).


class SlotMapperPort(ABC):
    """발화 + 역할별 후보 풀 → 역할별 (node_type, confidence) 매핑 (LLM 구조화 추출)."""

    @abstractmethod
    async def map_slots(
        self, utterance: str, roles_and_pools: dict[SlotRole, tuple[str, ...]]
    ) -> dict[SlotRole, tuple[tuple[str, float], ...]]:
        """각 역할 슬롯을 채울 node_type을 후보 풀 안에서 골라 confidence(0~1)와 함께 반환한다.

        Args:
            utterance: 사용자 발화.
            roles_and_pools: 확신 못 한 역할 → 그 역할 후보 풀(이 안에서만 선택, 환각 금지).

        Returns:
            역할 → ((node_type, confidence), …) relevance 순. 해당 역할에 적합 노드가 없으면
            빈 튜플(앙상블이 기권으로 처리). 풀 밖 node_type은 구현체가 폐기.
        """
        ...
