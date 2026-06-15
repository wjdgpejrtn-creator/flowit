"""렉시컬 엔티티 추출기 테스트 (ADR-0026 §6.6.3 step 1) — 순수·결정적이라 전수 검증."""
from __future__ import annotations

from ai_agent.domain.services.skeleton_entity_extractor import SkeletonEntityExtractor

_X = SkeletonEntityExtractor()


def test_schedule_trigger_detected() -> None:
    e = _X.extract("매주 월요일에 시트 읽어서 요약")
    assert e.trigger == "schedule_trigger"


def test_webhook_trigger_detected() -> None:
    assert _X.extract("웹훅 들어오면 처리").trigger == "webhook_trigger"


def test_event_trigger_detected() -> None:
    assert _X.extract("이벤트가 발생하면 알림").trigger == "event_trigger"


def test_no_trigger_keyword_returns_none() -> None:
    # 트리거 미지정 → None (조립기가 스켈레톤 default로 채움).
    assert _X.extract("내용 요약해서 슬랙으로").trigger is None


def test_sheet_source_forced_in() -> None:
    # e2e 버그 직격: "광고 시트"가 의미검색 아닌 렉시컬로 google_sheets_read 강제 진입.
    assert "google_sheets_read" in _X.extract("광고 시트 읽어서 요약").sources


def test_multiple_sources_ordered_by_appearance() -> None:
    e = _X.extract("빅쿼리 조회하고 구글 시트도 읽어서")
    assert e.sources == ("bigquery_query", "google_sheets_read")


def test_transform_dedup_to_single_ai() -> None:
    # 여러 변환 키워드("요약"+"분석")여도 동일 node_type은 1개로.
    assert _X.extract("요약하고 분석해서").transforms == ("gemma_chat",)


def test_ambiguous_transform_words_not_mapped_to_ai() -> None:
    # "변환/가공"은 결정적 transform(data_mapping 등) 의도와 겹쳐 AI 노드 오삽입을 부르므로
    # 렉시컬 매핑에서 제외(#435 리뷰 LOW). Phase 2 의미매칭이 디스앰비규에이션.
    assert _X.extract("json 데이터 변환해서 슬랙으로").transforms == ()
    assert _X.extract("데이터 가공해서 저장").transforms == ()


def test_slack_sink_detected() -> None:
    assert _X.extract("결과를 슬랙으로 보내줘").sinks == ("slack_post_message",)


def test_gmail_suppresses_generic_email() -> None:
    # gmail + 일반 메일 동시 매칭 시 더 구체적인 gmail_send만 남긴다(중복 채널 방지).
    e = _X.extract("gmail로 이메일 보내줘")
    assert "gmail_send" in e.sinks
    assert "email_send" not in e.sinks


def test_needs_gate_detected() -> None:
    assert _X.extract("품질 기준 통과할 때까지 재생성").needs_gate is True


def test_no_gate_when_absent() -> None:
    assert _X.extract("시트 읽어서 슬랙으로").needs_gate is False


def test_empty_entities_for_chitchat() -> None:
    assert _X.extract("안녕 반가워").is_empty() is True


def test_full_e2e_bug_utterance() -> None:
    e = _X.extract("매주 월요일에 광고 시트 읽어서 요약해서 슬랙으로 보내줘")
    assert e.trigger == "schedule_trigger"
    assert e.sources == ("google_sheets_read",)
    assert e.transforms == ("gemma_chat",)
    assert e.sinks == ("slack_post_message",)
    assert e.needs_gate is False
    assert e.has_branch is False
    assert e.has_fanout is False


def test_branch_signal_detected() -> None:
    e = _X.extract("긴급하면 슬랙, 아니면 이메일로 보내줘")
    assert e.has_branch is True
    assert e.shape_signals() == {"branch"}


def test_quarter_word_does_not_trigger_branch() -> None:
    # "분기(quarter, 시간단위)"는 "분기(branch)"와 동음이의 — 콘텐츠 발화를 branch 제어흐름으로
    # 오인하면 스켈레톤이 bail해 LLM 폴백(내부 gemma 기본값 미적용)된다. quarter 표현은 branch 신호 X.
    for utterance in (
        "매분기 말에 '분기 성과' 시트 읽어서 요약 보고서 작성해서 메일로 보내줘",
        "분기별 매출 요약해서 슬랙으로",
        "분기말 실적 보고서 작성",
    ):
        e = _X.extract(utterance)
        assert e.has_branch is False, utterance
        assert "branch" not in e.shape_signals(), utterance


def test_genuine_branch_verb_still_detected() -> None:
    # 분기 **동작**(동사 분기하다/분기시키다 + "분기 처리")은 활용형 전반에서 branch로 잡혀야 한다
    # (진짜 제어흐름 보존). 어간 매칭이라 여/서/ㄴ다/했다/줘/시켜 등 활용형을 두루 커버.
    for utterance in (
        "값에 따라 분기하여 처리해줘",
        "조건마다 분기해서 보내",
        "유형 보고 분기한다",
        "상태로 분기해줘",
        "등급으로 분기시켜",
        "값 보고 분기 처리해",
    ):
        e = _X.extract(utterance)
        assert e.has_branch is True, utterance
        assert "branch" in e.shape_signals(), utterance


def test_fanout_signal_detected() -> None:
    e = _X.extract("각 항목마다 요약해서 저장")
    assert e.has_fanout is True
    assert e.shape_signals() == {"fanout"}


def test_retry_signal_detected() -> None:
    e = _X.extract("API 호출 실패하면 재시도해줘")
    assert e.has_retry is True
    assert "retry" in e.shape_signals()


def test_approval_signal_detected() -> None:
    e = _X.extract("초안 검토 후 승인되면 발송")
    assert e.has_approval is True
    assert "approval" in e.shape_signals()


def test_guard_signal_detected() -> None:
    e = _X.extract("온도 값이 임계치를 넘으면 경보 메일을 보내줘")
    assert e.has_guard is True
    assert "guard" in e.shape_signals()


def test_guard_threshold_variants() -> None:
    for u in ("100을 초과하면 알림", "재고가 10개 이하이면 발주", "점수가 80 이상이면 통과 메일",
              "잔액이 0보다 작으면 경고", "목표치에 도달하면 보고"):
        assert _X.extract(u).has_guard is True, u


def test_guard_not_overactivated() -> None:
    # 가드 어휘 없는 발화는 has_guard False (빈출 "~면" 단독 과활성 금지 회귀 가드).
    for u in ("매주 시트 읽어서 슬랙으로", "안녕 반가워", "고객에게 안내 메일 보내줘",
              "회의록 정리해서 저장", "각 항목마다 요약"):
        assert _X.extract(u).has_guard is False, u


def test_plain_pipeline_has_no_shape_signal() -> None:
    e = _X.extract("매주 시트 읽어서 요약해서 슬랙으로 보내줘")
    assert e.shape_signals() == set()


# ── 어휘 갭 트랙 Phase 1 — 동의어/별칭 확장 ──────────────────────────────────
def test_docs_save_synonyms_capture_google_docs() -> None:
    # 데모서 놓쳤던 "docs 저장" — 이제 google_docs_write로 잡힌다.
    assert "google_docs_write" in _X.extract("결과를 docs 저장").sinks
    assert "google_docs_write" in _X.extract("요약해서 구글 문서로 저장").sinks


def test_schedule_synonyms() -> None:
    for u in ("매일 아침마다 실행", "주간으로 집계", "정각에 발송", "월간 리포트"):
        assert _X.extract(u).trigger == "schedule_trigger", u


def test_source_synonyms() -> None:
    assert "http_request" in _X.extract("엔드포인트에서 가져와서").sources
    assert "bigquery_query" in _X.extract("big query 조회").sources
    assert "google_sheets_read" in _X.extract("스프레드 시트 읽어서").sources


def test_sink_send_synonyms() -> None:
    assert "email_send" in _X.extract("메일로 발송").sinks
    assert "pdf_generate" in _X.extract("pdf로 저장").sinks
    assert "google_calendar_create_event" in _X.extract("캘린더에 일정 추가").sinks


def test_drive_file_dedup_drops_generic_file_read() -> None:
    # "드라이브 파일 읽어서"는 google_drive_read 1소스 — generic file_read 과추출 방지.
    sources = _X.extract("드라이브 파일 읽어서 요약").sources
    assert "google_drive_read" in sources
    assert "file_read" not in sources


def test_local_file_read_still_works() -> None:
    # 드라이브 언급이 없으면 generic file_read는 정상 동작(과교정 아님).
    assert "file_read" in _X.extract("파일을 읽어서 요약").sources


# ── 방향성 읽기 source + 소스-블리드 차단 (적대 검증 회귀 가드, §6.6.3) ───────────
def test_directional_read_sources_detected() -> None:
    # 양방향 서비스의 읽기 맥락 → read 변형이 source로 진입(이전엔 source 미인식 → 오선택).
    assert "gmail_read" in _X.extract("내 gmail에서 받은 견적 메일 모아서").sources
    assert "slack_read" in _X.extract("슬랙 공지 채널 글들 읽어서 요약").sources
    assert "linear_read" in _X.extract("리니어에 등록된 티켓들 긁어와서").sources
    assert "google_docs_read" in _X.extract("구글 닥스 문서 내용 읽어다가").sources
    assert "google_calendar_read" in _X.extract("구글 캘린더 이번주 일정 뽑아서").sources


def test_source_bleed_suppressed_slack_read_not_slack_sink() -> None:
    # "슬랙…읽어서…이메일로" — 슬랙은 source(읽기), sink는 이메일. slack_post_message 블리드 차단.
    e = _X.extract("슬랙 공지 채널 글들 읽어서 요약해서 이메일로 보내줘")
    assert "slack_read" in e.sources
    assert "slack_post_message" not in e.sinks and "slack_notify" not in e.sinks
    assert "email_send" in e.sinks


def test_source_bleed_suppressed_linear_read_not_linear_sink() -> None:
    # "리니어…긁어와서…슬랙에" — 리니어는 source, sink는 슬랙. linear_create_issue 블리드 차단.
    e = _X.extract("리니어에 등록된 티켓들 긁어와서 요약 보고서로 만들어 슬랙에")
    assert "linear_read" in e.sources
    assert "linear_create_issue" not in e.sinks
    assert "slack_post_message" in e.sinks


def test_source_bleed_suppressed_docs_read_not_docs_sink() -> None:
    e = _X.extract("구글 닥스 문서 내용 읽어다가 핵심만 추려서 슬랙에 올려줘")
    assert "google_docs_read" in e.sources
    assert "google_docs_write" not in e.sinks
    assert "slack_post_message" in e.sinks


def test_source_bleed_suppressed_calendar_read_not_calendar_sink() -> None:
    e = _X.extract("구글 캘린더 이번주 일정 쭉 뽑아서 정리해서 메일로 보내줘")
    assert "google_calendar_read" in e.sources
    assert "google_calendar_create_event" not in e.sinks


def test_dual_role_kept_when_send_cue_present() -> None:
    # "gmail에서 읽고 gmail로 회신" — 양끝 정당(read source + send sink). send-cue 있으면 유지.
    e = _X.extract("gmail에서 받은 견적 메일 모아서 정리한 다음 다시 gmail로 회신 보내줘")
    assert "gmail_read" in e.sources
    assert "gmail_send" in e.sinks  # send-cue "gmail로" → 미차단


def test_write_only_service_not_falsely_source() -> None:
    # 쓰기 전용("…에 저장/등록")은 read source로 오인 안 함(읽기 맥락 토큰 부재).
    assert "google_docs_read" not in _X.extract("보고서 생성해서 구글 docs에 저장").sources
    assert "google_calendar_create_event" in _X.extract("일정 잡아서 캘린더에 등록").sinks


def test_elided_send_verb_slack_sink_preserved() -> None:
    # "슬랙이랑 이메일 둘 다 보내줘" — 슬랙은 read 맥락 아님 → 차단 안 됨, sink 유지(생략 동사 견고).
    e = _X.extract("매주 시트 읽어서 슬랙이랑 이메일 둘 다 보내줘")
    assert "slack_post_message" in e.sinks
