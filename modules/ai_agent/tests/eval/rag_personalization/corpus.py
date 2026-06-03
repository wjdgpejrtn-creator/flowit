"""RAG 효용성 검증용 페르소나 시드 corpus.

가상의 한 사용자(사무직 직장인)가 personalization에 누적했을 법한 업무 패턴 6종.
각 패턴은 GCS에 저장되는 MemoryFile 형태 그대로 — RecallPersonalSkillsUseCase가
load_index/load_file로 읽어가는 단위와 동일하다.

이 corpus는 임베딩과 무관하다(텍스트만). 실제 BGE-M3 임베딩은 capture_embeddings.py가
한 번 떠서 snapshots/에 골든 스냅샷으로 커밋한다.
"""
from __future__ import annotations

from ai_agent.domain.entities.memory_file import MemoryFile


def _file(name: str, memory_type: str, description: str, body: str) -> MemoryFile:
    return MemoryFile(
        filename=f"{name}.md",
        name=name,
        description=description,
        memory_type=memory_type,  # type: ignore[arg-type]
        body=body,
    )


# 가상 사용자의 누적 업무 패턴 (정답지 scenarios.py가 이 name들을 참조한다)
PERSONA_CORPUS: list[MemoryFile] = [
    _file(
        "doc_tool_hwp",
        "user",
        "문서 작성 도구 선호 — 한글(HWP)",
        "문서나 보고서를 작성할 때는 항상 아래아한글(HWP/HWPX)을 사용한다. "
        "MS Word 대신 한글로 작성하고 .hwp 형식으로 저장해 공유한다. "
        "표·결재란이 들어간 사내 문서는 전부 한글 양식 기반이다.",
    ),
    _file(
        "mail_client_outlook",
        "user",
        "이메일 클라이언트 — Outlook",
        "이메일은 사내 Microsoft Outlook으로 보낸다. 외부 고객사로 나가는 안내 메일도 "
        "Outlook 서명을 붙여 발송하며, 수신확인을 켜둔다.",
    ),
    _file(
        "report_schedule_weekly",
        "project",
        "주간 보고 루틴 — 매주 금요일",
        "주간 업무 보고서는 매주 금요일 오후에 작성해 팀장에게 제출한다. "
        "정해진 주간보고 템플릿(이번 주 한 일 / 다음 주 계획 / 이슈)을 사용한다.",
    ),
    _file(
        "data_google_sheets",
        "user",
        "데이터 정리 도구 — 구글 시트",
        "매출·실적 같은 수치 데이터는 구글 스프레드시트에 정리한다. "
        "피벗 테이블로 월별 집계를 내고 차트를 첨부해 공유한다.",
    ),
    _file(
        "meeting_notes_notion",
        "user",
        "회의록 정리 — Notion",
        "회의록은 Notion의 회의록 데이터베이스에 정리한다. 회의가 끝나면 "
        "결정 사항과 액션 아이템을 표로 만들어 담당자를 지정한다.",
    ),
    _file(
        "announce_slack_general",
        "project",
        "사내 공지 채널 — Slack #general",
        "사내 전체 공지는 Slack의 #general 채널에 올린다. 중요한 공지는 @here로 "
        "멘션해 알린다.",
    ),
]

CORPUS_BY_NAME: dict[str, MemoryFile] = {f.name: f for f in PERSONA_CORPUS}
ALL_NAMES: frozenset[str] = frozenset(CORPUS_BY_NAME)
