"""발화 시나리오 + 정답지.

해당 사용자가 실제로 칠 법한 자연어 발화와, 그 발화에 대해 personalization RAG가
떠올려야 마땅한 패턴(corpus name)을 매핑한 정답지.

- primary: 반드시 top-k에 들어야 하는 핵심 패턴 (hit@k 판정 기준)
- secondary: 들면 가점이지만 필수는 아닌 패턴
- distractor=True: 업무와 무관 → RAG가 min_score 게이트로 '빈손' 반환해야 정답
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scenario:
    utterance: str
    intent_label: str  # _fast_classify가 붙일 법한 IntentType.value (쿼리 보강용)
    primary: frozenset[str] = field(default_factory=frozenset)
    secondary: frozenset[str] = field(default_factory=frozenset)
    distractor: bool = False

    @property
    def gold(self) -> frozenset[str]:
        return self.primary | self.secondary


SCENARIOS: list[Scenario] = [
    Scenario(
        utterance="이번 주 주간 보고서 자동으로 작성해줘",
        intent_label="draft",
        primary=frozenset({"report_schedule_weekly"}),
        secondary=frozenset({"doc_tool_hwp"}),
    ),
    Scenario(
        utterance="보고서 문서 하나 만들어줘",
        intent_label="draft",
        primary=frozenset({"doc_tool_hwp"}),
    ),
    Scenario(
        utterance="고객사에 안내 메일 발송하는 거 자동화하고 싶어",
        intent_label="draft",
        primary=frozenset({"mail_client_outlook"}),
    ),
    Scenario(
        utterance="이번 달 매출 데이터 정리해서 표로 만들어줘",
        intent_label="draft",
        primary=frozenset({"data_google_sheets"}),
    ),
    Scenario(
        utterance="회의 끝나면 회의록 정리해서 저장해줘",
        intent_label="draft",
        primary=frozenset({"meeting_notes_notion"}),
    ),
    Scenario(
        utterance="팀 전체한테 공지 하나 돌려줘",
        intent_label="draft",
        primary=frozenset({"announce_slack_general"}),
    ),
    Scenario(
        utterance="점심 뭐 먹는 게 좋을까",
        intent_label="chitchat",
        distractor=True,
    ),
]


def build_query(scenario: Scenario) -> str:
    """의도분석 결과 기반 쿼리 문자열 생성.

    IntentResult는 카테고리 enum + (fast-path에선 빈) analyzed_entities뿐이라
    의미 정보가 거의 없다. 따라서 쿼리는 발화 본문(의미 내용)을 핵심으로 하고,
    intent 라벨은 약한 컨텍스트로만 덧붙인다. (진입점 확인 결과 — 2번 단계)
    """
    return scenario.utterance
