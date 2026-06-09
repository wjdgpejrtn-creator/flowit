from __future__ import annotations

from ..value_objects.skeleton import ExtractedEntities

# 발화 → 슬롯 충전 재료 추출기 (ADR-0026 §6.6.3 step 1) — 순수·결정적·렉시컬.
#
# "코드가 구조를 결정한다"의 입구. 발화에 명시된 도메인 노드(예: "광고 시트"→
# google_sheets_read)를 의미검색 랭킹에 맡기지 않고 렉시컬로 직접 잡아 슬롯에 강제 진입
# 시킨다(#418 always-include의 일반화). 의미 임베딩 보강은 후속(Modal) — 본 추출기는
# Modal 불요로 오프라인 단위테스트가 가능한 렉시컬 백본이다.
#
# 매핑 대상 node_type은 전부 카탈로그(53종)에 실재. 키워드는 한국어 업무 발화에서 실제
# 등장하는 표현으로, 과활성을 피하려 충분히 구체적인 토큰만 둔다(짧은 부분문자열 주의).

# ── 트리거(단수, 우선순위 순) ───────────────────────────────────────────────
# 첫 매칭이 트리거를 결정한다. 미매칭이면 None → 조립기가 스켈레톤 default로 채운다.
_TRIGGER_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("schedule_trigger", ("매주", "매일", "매월", "매시간", "매분", "정기적", "주기적", "스케줄", "요일", "정기")),
    ("webhook_trigger", ("웹훅", "webhook")),
    ("file_watch_trigger", ("파일이 올라오면", "파일 감지", "업로드되면", "파일이 생성되면")),
    ("event_trigger", ("이벤트가", "이벤트 발생", "발생하면", "수신하면", "들어오면")),
    ("api_poll_trigger", ("폴링", "주기적으로 확인", "주기적으로 조회")),
)

# ── 소스(복수, 발화 등장 순) ────────────────────────────────────────────────
_SOURCE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("google_sheets_read", ("스프레드시트", "구글 시트", "google sheet", "시트", "sheets")),
    ("google_drive_read", ("구글 드라이브", "google drive", "드라이브")),
    ("bigquery_query", ("빅쿼리", "bigquery")),
    ("postgresql_query", ("postgresql", "postgres", "포스트그레")),
    ("mysql_query", ("mysql", "마이에스큐엘")),
    ("graphql", ("graphql",)),
    ("rest_api", ("rest api", "rest 호출")),
    ("http_request", ("http 요청", "http 호출", "api에서", "api 호출", "api를 호출", "외부 api")),
    ("file_read", ("파일을 읽", "파일 읽", "파일에서 읽")),
)

# ── 변환(복수지만 node_type 중복 제거 — 통상 ai 1개) ─────────────────────────
_TRANSFORM_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("anthropic_chat", ("요약", "생성", "작성", "초안", "분석", "분류", "번역", "정리", "답변 작성", "추출해")),
)

# ── 싱크(복수, 발화 등장 순) ────────────────────────────────────────────────
_SINK_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("slack_post_message", ("slack", "슬랙")),
    ("gmail_send", ("gmail", "지메일")),
    ("email_send", ("이메일", "메일", "email")),
    ("google_docs_write", ("구글 docs", "google docs", "구글 문서", "문서로 저장", "docs에")),
    ("pdf_generate", ("pdf",)),
    ("linear_create_issue", ("linear", "리니어", "이슈 생성", "이슈를 생성")),
    ("google_calendar_create_event", ("캘린더", "일정 등록", "calendar")),
    ("file_write", ("파일로 저장", "파일로 내보", "파일에 저장")),
)

# ── 게이트(검증 루프 함의) ──────────────────────────────────────────────────
_GATE_KEYWORDS: tuple[str, ...] = (
    "통과할 때까지", "만족할 때까지", "기준에 맞을 때까지", "기준 충족",
    "검증", "품질", "재생성", "반복 개선", "개선해서", "점수가", "퀄리티",
)

# ── 미지원 shape 신호 (현 라이브러리=선형/루프만) ─────────────────────────────
# 잡히면 조립기가 LLM으로 bail — 억지 선형 납작화 방지. 향후 branch/fan_out 스켈레톤이
# 생기면 라우팅 신호로 승격(ADR-0026 §6.6 확장). 과활성을 피해 분기/병렬을 명확히 가리키는
# 구절만 둔다(예: 단독 "면"은 "하면/되면" 등 빈출이라 금지, "아니면"처럼 양자택일만).
_BRANCH_KEYWORDS: tuple[str, ...] = (
    "아니면", "아니라면", "그렇지 않으면", "그 외에는", "경우에 따라", "에 따라 다르",
    "분기", "조건에 따라", "라면 ", "이라면 ",
)
_FANOUT_KEYWORDS: tuple[str, ...] = (
    "각각", "각 항목", "항목마다", "항목별", "그룹별", "건마다", "건별", "개별적으로",
    "전부 각", "하나하나", "병렬",
)
_RETRY_KEYWORDS: tuple[str, ...] = (
    "재시도", "실패하면", "실패 시", "실패하면 다시", "안 되면 다시", "다시 시도",
    "될 때까지 재시도", "오류 나면",
)
_APPROVAL_KEYWORDS: tuple[str, ...] = (
    "승인", "검토 후", "컨펌", "결재", "허가", "승인되면", "승인받아", "결재 후",
)


def _match_single(text: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    """우선순위 순으로 첫 매칭 node_type 반환(트리거용)."""
    for node_type, keywords in rules:
        if any(kw in text for kw in keywords):
            return node_type
    return None


def _match_ordered(text: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> tuple[str, ...]:
    """매칭된 node_type을 발화 등장 위치 순으로(중복 제거) 반환(소스/싱크용).

    한 node_type의 위치 = 그 node_type 키워드 중 가장 먼저 등장한 위치. 위치 동률이면
    rules 정의 순서로 안정 정렬(결정적).
    """
    hits: list[tuple[int, int, str]] = []
    for order, (node_type, keywords) in enumerate(rules):
        positions = [text.find(kw) for kw in keywords if kw in text]
        if positions:
            hits.append((min(positions), order, node_type))
    hits.sort()
    return tuple(node_type for _, _, node_type in hits)


class SkeletonEntityExtractor:
    """발화에서 슬롯 충전 재료를 뽑는 순수 렉시컬 추출기 (ADR-0026 §6.6.3).

    의존 없음(LLM/임베딩 불요) — 결정적이라 단위테스트로 전수 검증한다. 의미검색 기반
    보강(동의어·오타 내성)은 Modal 복귀 후 하이브리드로 덧댄다.
    """

    def extract(self, utterance: str) -> ExtractedEntities:
        text = utterance.lower()
        sinks = _match_ordered(text, _SINK_RULES)
        # gmail과 generic email이 동시 매칭되면 더 구체적인 gmail_send만 남긴다(중복 채널 방지).
        if "gmail_send" in sinks and "email_send" in sinks:
            sinks = tuple(s for s in sinks if s != "email_send")
        return ExtractedEntities(
            trigger=_match_single(text, _TRIGGER_RULES),
            sources=_match_ordered(text, _SOURCE_RULES),
            transforms=_match_ordered(text, _TRANSFORM_RULES),
            sinks=sinks,
            needs_gate=any(kw in text for kw in _GATE_KEYWORDS),
            has_branch=any(kw in text for kw in _BRANCH_KEYWORDS),
            has_fanout=any(kw in text for kw in _FANOUT_KEYWORDS),
            has_retry=any(kw in text for kw in _RETRY_KEYWORDS),
            has_approval=any(kw in text for kw in _APPROVAL_KEYWORDS),
        )
