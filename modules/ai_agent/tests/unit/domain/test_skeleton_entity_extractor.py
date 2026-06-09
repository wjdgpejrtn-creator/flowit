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
    assert _X.extract("요약하고 분석해서").transforms == ("anthropic_chat",)


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
    assert e.transforms == ("anthropic_chat",)
    assert e.sinks == ("slack_post_message",)
    assert e.needs_gate is False
    assert e.has_branch is False
    assert e.has_fanout is False


def test_branch_signal_detected() -> None:
    e = _X.extract("긴급하면 슬랙, 아니면 이메일로 보내줘")
    assert e.has_branch is True
    assert e.shape_signals() == {"branch"}


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
