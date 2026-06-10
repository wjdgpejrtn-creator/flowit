from __future__ import annotations

from pydantic import BaseModel

from ...domain.ports.llm_port import LLMPort
from ...domain.ports.slot_mapper_port import SlotMapperPort
from ...domain.value_objects.skeleton import SlotRole

# LLM 슬롯 매퍼 (ADR-0026 §6.6 Phase 2 — 앙상블 LLM voter 구현).
#
# EnsembleSlotResolver가 싼 voter(lexical/semantic/ontology)로 확신 못 한 SOURCE/SINK 역할만
# 지연 escalation으로 호출한다. Gemma(LLMPort.generate_structured)가 발화의 **방향성**을
# 읽어 후보 풀 안에서 역할별 노드를 고른다 — "gmail에서"(읽기)=source gmail_read vs "gmail로
# 보내"(쓰기)=sink gmail_send처럼 같은 서비스라도 방향으로 갈린다. ADR-0013 EmbedderPort
# 예외 패턴: Modal LLM 호출 어댑터는 호출 모듈(ai_agent)이 보유.

_SYSTEM_PROMPT = """You map workflow slots to node types from the user's request.
For each slot role, pick the ONE best node_type from THAT role's candidate list — or omit the
role entirely if no candidate genuinely fits.

Role meanings (mind the DIRECTION):
- source: where the workflow READS / COLLECTS data FROM. Korean cues: "…에서", "…읽어", "…조회",
  "받은 …". English: "read X", "from X".
- sink: where the workflow SENDS / WRITES output TO. Korean cues: "…로 보내", "…에 저장", "…로 발송".
  English: "send to X", "save to X".
The SAME service can appear as a source in one slot and a sink in another (read Gmail → send Gmail):
choose by direction, not by the service name alone.

Rules:
- Use ONLY node_types listed for each role. Never invent a node_type.
- confidence is your certainty in [0,1].
- Omit a role from the output if no candidate fits the user's intent.
Output JSON only: {"slots": [{"role": "source", "node_type": "gmail_read", "confidence": 0.9}]}."""


class _SlotPick(BaseModel):
    role: str
    node_type: str
    confidence: float = 0.0


class _SlotMapResponse(BaseModel):
    slots: list[_SlotPick] = []


class LlmSlotMapper(SlotMapperPort):
    """Gemma 구조화 추출로 역할별 후보 풀 안에서 노드를 고른다(방향성 디스앰비규에이션)."""

    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def map_slots(
        self, utterance: str, roles_and_pools: dict[SlotRole, tuple[str, ...]]
    ) -> dict[SlotRole, tuple[tuple[str, float], ...]]:
        if not roles_and_pools:
            return {}
        lines = [f"User request: {utterance}", "", "Slots to fill:"]
        for role, pool in roles_and_pools.items():
            lines.append(f"- {role.value}: candidates = {list(pool)}")
        prompt = _SYSTEM_PROMPT + "\n\n" + "\n".join(lines)

        try:
            resp = await self._llm.generate_structured(prompt, _SlotMapResponse)
        except Exception:
            # escalation 실패는 비치명적 — 싼 voter 결과가 그대로 선다(앙상블 graceful degrade).
            return {}

        role_by_value = {r.value: r for r in roles_and_pools}
        pool_by_value = {r.value: set(p) for r, p in roles_and_pools.items()}
        grouped: dict[SlotRole, list[tuple[str, float]]] = {}
        for pick in resp.slots:
            role = role_by_value.get(pick.role)
            if role is None or pick.node_type not in pool_by_value.get(pick.role, set()):
                continue  # 미지정 역할 / 풀 밖 node_type = 환각 폐기
            conf = max(0.0, min(1.0, pick.confidence))
            grouped.setdefault(role, []).append((pick.node_type, conf))
        return {
            role: tuple(sorted(picks, key=lambda x: -x[1]))
            for role, picks in grouped.items()
        }
