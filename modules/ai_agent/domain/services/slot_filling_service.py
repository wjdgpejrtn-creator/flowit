from __future__ import annotations

from typing import Optional

from common_schemas import DraftSpec, SlotFillingState

_SLOT_QUESTIONS: dict[str, str] = {
    "tool": "어떤 도구를 사용하시겠어요? (예: Gmail, Slack, Google Drive)",
    "trigger": "언제/어떤 조건으로 실행할까요? (예: 매일 오전 9시, 새 파일이 생겼을 때)",
    "output": "결과를 어디에 전달할까요? (예: Slack 채널, 이메일)",
    "target": "대상이 누구인가요? (예: 팀 전체, 특정 사용자)",
    "frequency": "얼마나 자주 실행할까요? (예: 매일, 매주, 실시간)",
}


class SlotFillingService:
    """순수 도메인 로직 — LLM 의존 없음."""

    def next_question(self, state: SlotFillingState, spec: DraftSpec) -> Optional[str]:
        """다음으로 물어봐야 할 슬롯의 질문을 반환한다. 모두 채워졌으면 None."""
        for slot in state.pending:
            if slot not in state.filled:
                return _SLOT_QUESTIONS.get(slot, f"'{slot}'에 대해 알려주세요.")
        return None

    def is_complete(self, state: SlotFillingState) -> bool:
        return not state.pending or all(s in state.filled for s in state.pending)
