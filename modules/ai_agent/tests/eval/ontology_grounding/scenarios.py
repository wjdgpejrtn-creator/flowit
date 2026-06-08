"""골든 요청셋 + 정답지 (ADR-0026 §6.5).

사용자가 실제로 칠 법한 자연어 워크플로우 요청과, composer가 마땅히 만들어야 할
구조적 기대치를 매핑한다. 라이브 캡처(run_eval)가 각 발화를 실 composer로 돌려
산출 워크플로우를 RunRecord로 정규화하고, metrics가 아래 기대치 대비 채점한다.

채점 축(§6.5):
  - expected_motif="quality_gate_loop" → 산출물이 **실행가능 루프**(back-edge + condition
    노드 ≥1, validator §2 SCC 수용기준 정합)를 만들어야 motif-correct.
  - expected_motif=None(선형/분기) → 모티프 강제 없음. validator-pass / 비환각만 본다.
  - distractor=True(잡담) → 워크플로우를 만들지 **않아야** 정답(chitchat fast-path).

> 발화는 의도적으로 다양한 도메인(메일/시트/문서/슬랙/캘린더/HTTP)에 걸쳐 두어
> 카탈로그 그라운딩 폭을 측정한다. node hint는 약한 참고용(정확매칭 강제 아님) —
> 산출 node_type이 카탈로그(EXECUTABLE_NODE_TYPES)에 있으면 비환각으로 본다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

QUALITY_GATE_LOOP = "quality_gate_loop"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    utterance: str
    expected_motif: str | None = None
    distractor: bool = False
    # 약한 참고용 — 산출물에 한 번쯤 떠야 자연스러운 node_type(채점 강제 아님, 진단용).
    node_hints: frozenset[str] = field(default_factory=frozenset)

    @property
    def expects_workflow(self) -> bool:
        """잡담이 아니면 워크플로우를 만들어야 한다."""
        return not self.distractor


# 골든셋 — §6.5 권장 30~50건 규모. 루프(품질검증) 포함 균형 배치.
SCENARIOS: list[Scenario] = [
    # ── 품질검증 루프 모티프(quality_gate_loop) — 8건 ─────────────────────────
    Scenario(
        "loop_report_quality",
        "주간 보고서를 작성하되 품질이 8점 넘을 때까지 다시 고쳐서 완성해줘",
        expected_motif=QUALITY_GATE_LOOP,
        node_hints=frozenset({"anthropic_chat", "if_condition"}),
    ),
    Scenario(
        "loop_translation_review",
        "영어 번역문을 만들고 검수해서 통과 못 하면 다시 번역 반복해줘",
        expected_motif=QUALITY_GATE_LOOP,
        node_hints=frozenset({"anthropic_chat", "if_condition"}),
    ),
    Scenario(
        "loop_email_draft_check",
        "고객 안내 메일 초안을 쓰고 톤 검토를 통과할 때까지 다듬은 뒤 발송해줘",
        expected_motif=QUALITY_GATE_LOOP,
        node_hints=frozenset({"anthropic_chat", "if_condition", "email_send"}),
    ),
    Scenario(
        "loop_summary_until_good",
        "회의록을 요약하고 누락이 없을 때까지 요약을 보완 반복해줘",
        expected_motif=QUALITY_GATE_LOOP,
        node_hints=frozenset({"anthropic_chat", "if_condition"}),
    ),
    Scenario(
        "loop_code_review_cycle",
        "코드 리뷰 코멘트를 생성하고 기준 점수 미달이면 재생성하는 루프로 만들어줘",
        expected_motif=QUALITY_GATE_LOOP,
        node_hints=frozenset({"anthropic_chat", "if_condition"}),
    ),
    Scenario(
        "loop_blog_polish",
        "블로그 글을 쓰고 자체 평가 점수가 만족스러울 때까지 퇴고를 반복해줘",
        expected_motif=QUALITY_GATE_LOOP,
        node_hints=frozenset({"anthropic_chat", "if_condition"}),
    ),
    Scenario(
        "loop_spec_refine",
        "기능 명세서를 초안 작성하고 검증 통과 전까지 반복 보완해줘",
        expected_motif=QUALITY_GATE_LOOP,
        node_hints=frozenset({"anthropic_chat", "if_condition"}),
    ),
    Scenario(
        "loop_qa_until_pass",
        "답변을 생성하고 품질 게이트를 통과할 때까지 다시 답변 생성을 돌려줘",
        expected_motif=QUALITY_GATE_LOOP,
        node_hints=frozenset({"anthropic_chat", "if_condition"}),
    ),
    # ── 선형 초안(모티프 없음) — 16건 ─────────────────────────────────────────
    Scenario("lin_weekly_report", "이번 주 주간 보고서 자동으로 작성해줘",
             node_hints=frozenset({"anthropic_chat", "google_docs_write"})),
    Scenario("lin_make_doc", "보고서 문서 하나 만들어줘",
             node_hints=frozenset({"google_docs_write"})),
    Scenario("lin_customer_mail", "고객사에 안내 메일 발송하는 거 자동화하고 싶어",
             node_hints=frozenset({"email_send"})),
    Scenario("lin_sales_table", "이번 달 매출 데이터 정리해서 표로 만들어줘",
             node_hints=frozenset({"google_sheets_read", "csv_build"})),
    Scenario("lin_meeting_notes", "회의 끝나면 회의록 정리해서 저장해줘",
             node_hints=frozenset({"anthropic_chat", "file_write"})),
    Scenario("lin_team_announce", "팀 전체한테 슬랙으로 공지 하나 돌려줘",
             node_hints=frozenset({"slack_post_message"})),
    Scenario("lin_calendar_event", "다음 주 미팅 일정을 캘린더에 등록해줘",
             node_hints=frozenset({"google_calendar_create_event"})),
    Scenario("lin_fetch_summarize", "이 URL 내용을 가져와서 요약해줘",
             node_hints=frozenset({"http_request", "anthropic_chat"})),
    Scenario("lin_sheet_to_mail", "구글시트 데이터를 읽어서 요약 메일로 보내줘",
             node_hints=frozenset({"google_sheets_read", "anthropic_chat", "email_send"})),
    Scenario("lin_csv_parse", "업로드한 CSV를 파싱해서 항목별로 정리해줘",
             node_hints=frozenset({"csv_parse"})),
    Scenario("lin_daily_digest", "매일 아침 9시에 뉴스 요약을 메일로 받아보고 싶어",
             node_hints=frozenset({"schedule_trigger", "http_request", "anthropic_chat", "email_send"})),
    Scenario("lin_doc_to_slack", "문서를 읽고 핵심만 슬랙 채널에 공유해줘",
             node_hints=frozenset({"google_drive_read", "anthropic_chat", "slack_post_message"})),
    Scenario("lin_translate_send", "이 문장을 영어로 번역해서 메일로 보내줘",
             node_hints=frozenset({"anthropic_chat", "email_send"})),
    Scenario("lin_form_to_sheet", "웹훅으로 들어온 폼 응답을 시트에 적어줘",
             node_hints=frozenset({"webhook_trigger", "google_sheets_read"})),
    Scenario("lin_pdf_extract", "PDF에서 표를 추출해서 CSV로 저장해줘",
             node_hints=frozenset({"file_read", "csv_build"})),
    Scenario("lin_notify_on_event", "이벤트가 들어오면 담당자에게 메일 알림 보내줘",
             node_hints=frozenset({"event_trigger", "email_send"})),
    # ── 조건 분기(if_condition, 루프 아님) — 4건 ──────────────────────────────
    Scenario("branch_amount_route", "결제 금액이 100만원 넘으면 승인 요청, 아니면 자동 처리해줘",
             node_hints=frozenset({"if_condition", "email_send"})),
    Scenario("branch_sentiment", "고객 문의 감정을 분류해서 부정이면 매니저에게 에스컬레이션해줘",
             node_hints=frozenset({"anthropic_chat", "if_condition", "slack_post_message"})),
    Scenario("branch_category_switch", "문서 종류에 따라 다른 폴더에 저장되게 분기해줘",
             node_hints=frozenset({"switch_case"})),
    Scenario("branch_threshold_alert", "온도 값이 임계치를 넘으면 경보 메일을 보내줘",
             node_hints=frozenset({"if_condition", "email_send"})),
    # ── 잡담 distractor(워크플로우 생성 금지) — 4건 ───────────────────────────
    Scenario("chit_lunch", "점심 뭐 먹는 게 좋을까", distractor=True),
    Scenario("chit_greeting", "안녕 반가워", distractor=True),
    Scenario("chit_weather", "오늘 날씨 어때?", distractor=True),
    Scenario("chit_thanks", "고마워 도움이 됐어", distractor=True),
]


def by_id(scenario_id: str) -> Scenario:
    for s in SCENARIOS:
        if s.scenario_id == scenario_id:
            return s
    raise KeyError(scenario_id)
