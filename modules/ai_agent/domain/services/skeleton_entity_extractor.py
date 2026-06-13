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
#
# 어휘 갭 트랙 Phase 1 (ADR-0026 §6.6, 2026-06-09) — 동의어/별칭 확장으로 다양한 발화의
# 도메인 노드 진입률을 높여 LLM 폴백(구조 환각 위험) 표면을 줄인다. 오타·신규 표현 내성
# (의미매칭 하이브리드)은 Phase 2(BGE-M3, Modal)에서 덧댄다. 모호 매핑("데이터베이스"→어느
# DB?)은 잘못된 node_type을 강제하므로 렉시컬엔 넣지 않고 Phase 2 의미 디스앰비규에이션에 맡긴다.

# ── 트리거(단수, 우선순위 순) ───────────────────────────────────────────────
# 첫 매칭이 트리거를 결정한다. 미매칭이면 None → 조립기가 스켈레톤 default로 채운다.
_TRIGGER_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("schedule_trigger", (
        "매주", "매일", "매월", "매시간", "매분", "매년", "정기적", "주기적", "스케줄", "스케줄러",
        "요일", "정기", "주간", "일간", "월간", "아침마다", "정각", "cron", "크론", "정해진 시간",
    )),
    ("webhook_trigger", ("웹훅", "webhook", "web hook", "훅이 호출", "콜백 받으면")),
    ("file_watch_trigger", (
        "파일이 올라오면", "파일 감지", "업로드되면", "파일이 생성되면", "파일이 추가되면", "새 파일",
    )),
    ("event_trigger", (
        "이벤트가", "이벤트 발생", "발생하면", "수신하면", "들어오면", "도착하면", "트리거되면", "발생 시",
    )),
    ("api_poll_trigger", ("폴링", "주기적으로 확인", "주기적으로 조회", "일정 간격으로")),
)

# ── 소스(복수, 발화 등장 순) ────────────────────────────────────────────────
# 양방향(read/write) 서비스(gmail·slack·linear·docs·calendar)는 **읽기 방향 토큰만** source에
# 둔다 — bare 이름("슬랙"/"리니어"/"gmail")은 sink가 갖고, source는 "…에서"·읽기 동사 맥락으로만
# 진입(한국어 격조사 에서=출발/source vs 로·에=도착/sink). 같은 서비스가 source·sink 양끝일 수
# 있으므로(gmail 읽고 gmail 발송), 소스-블리드 차단은 _suppress_source_bleed가 send-cue 부재 시
# write-variant를 sink에서 제거해 처리. 미등록 변형은 semantic voter가 보강.
_SOURCE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gmail_read", (
        "gmail에서", "지메일에서", "지메일 인박스", "메일함", "받은 메일", "받은 편지함",
        "받은 견적", "인박스", "메일을 읽", "메일 읽", "이메일 읽", "메일 조회", "메일을 조회",
        "메일 가져", "메일들 모아", "메일들 훑", "메일들 싹",
    )),
    ("slack_read", (
        "슬랙에서", "슬랙 공지", "슬랙 채널 글", "슬랙 채널의", "슬랙 메시지 읽", "슬랙 글 읽",
        "슬랙에 올라온", "슬랙 스레드", "슬랙 대화",
    )),
    ("linear_read", (
        "리니어에서", "리니어에 등록된", "리니어 이슈 읽", "리니어 이슈 조회", "리니어 티켓 읽",
        "리니어에 있는", "리니어 긁",
    )),
    ("google_docs_read", (
        "닥스에서", "구글 닥스 문서", "닥스 문서", "문서 내용 읽", "문서 내용을 읽", "구글 문서 읽",
        "닥스 내용", "구글독스 문서",
    )),
    ("google_calendar_read", (
        "캘린더에서", "구글 캘린더 일정", "캘린더 일정 뽑", "캘린더 일정 조회", "캘린더의 일정",
        "일정 뽑아", "일정 가져", "일정 조회", "구글 캘린더 이번", "구글 캘린더 다음", "구글 캘린더 오늘",
    )),
    ("google_sheets_read", (
        "스프레드시트", "스프레드 시트", "구글 시트", "구글시트", "google sheet", "시트", "sheets",
    )),
    ("google_drive_read", ("구글 드라이브", "구글드라이브", "google drive", "드라이브")),
    ("bigquery_query", ("빅쿼리", "bigquery", "big query")),
    ("postgresql_query", ("postgresql", "postgres", "포스트그레", "pg에서", "pg 테이블")),
    ("mysql_query", ("mysql", "마이에스큐엘", "마이sql")),
    ("graphql", ("graphql", "그래프ql")),
    ("rest_api", ("rest api", "rest 호출", "rest로")),
    ("http_request", (
        "http 요청", "http 호출", "http로", "api에서", "api 호출", "api를 호출", "api로부터",
        "외부 api", "엔드포인트", "외부에서 가져",
    )),
    ("file_read", ("파일을 읽", "파일 읽", "파일에서 읽", "파일 내용", "파일로부터")),
)

# ── 변환(복수지만 node_type 중복 제거 — 통상 ai 1개) ─────────────────────────
# transform 슬롯 후보는 _AI(anthropic_chat/gemma_chat)뿐이므로, 여기 키워드는 **명백히 LLM
# 가공**을 가리키는 것만 둔다. "변환/가공"처럼 결정적 transform(data_mapping/json_transform,
# category=transform) 의도와 겹치는 광의어는 AI 노드 오삽입을 부르므로 제외 — 해당 디스앰비규에이션은
# Phase 2 의미매칭 몫(#435 리뷰 LOW 대응). 슬롯 미충전 시 조립기가 처리(transform 대개 optional).
_TRANSFORM_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gemma_chat", (
        "요약", "요약본", "생성", "작성", "초안", "분석", "분류", "번역", "정리", "답변 작성",
        "추출해", "응답 생성", "내용 생성", "텍스트 생성", "보고서 작성", "재작성", "다듬", "교정", "평가해",
        # 계산/집계 의도 — 결정적 글루노드(number_calc)는 스켈레톤 슬롯 후보가 아니므로(_AI만),
        # "전주 대비 증감 계산" 류는 AI transform이 데이터로부터 산출한다(박아름 #438 합의). source→
        # AI transform→sink 풀체인을 위한 명시 신호 — 이 의도는 retriever가 변별 못 함(core LLM
        # 노드 항상 후보, #418)이라 렉시컬에만 존재(#453 S-AREUM-2: "증감 계산" 슬롯 미충전 회귀).
        "계산", "증감", "집계", "산출",
    )),
)

# ── 싱크(복수, 발화 등장 순) ────────────────────────────────────────────────
_SINK_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("slack_post_message", ("slack", "슬랙")),
    ("gmail_send", ("gmail", "지메일")),
    ("email_send", ("이메일", "메일", "email")),
    ("google_docs_write", (
        "구글 docs", "google docs", "구글 문서", "구글닥스", "구글 닥스", "문서로 저장",
        "문서에 저장", "문서로 기록", "docs", "닥스에", "문서 만들", "문서 생성", "문서 하나",
    )),
    ("pdf_generate", ("pdf", "피디에프")),
    ("linear_create_issue", ("linear", "리니어", "이슈 생성", "이슈를 생성", "이슈로 등록", "티켓 생성")),
    ("google_calendar_create_event", ("캘린더", "일정 등록", "일정 추가", "일정 잡", "calendar")),
    ("file_write", ("파일로 저장", "파일로 내보", "파일에 저장", "파일로 출력", "파일에 기록")),
)

# 양방향 서비스 소스-블리드 차단: read_node → ((write_node, send_cues), …).
# read 변형이 source로 잡혔는데 그 write_node의 **send-cue(도착 격조사/발송 동사)가 발화에
# 없으면** 그 write를 sink에서 제거 — "슬랙 공지 읽어서…"의 슬랙이 slack_post_message로 새는 것
# 차단. send-cue가 있으면(예 "gmail에서 읽고 gmail로 회신") 유지(양끝 정당). **채널별(per-write)
# cue** — "gmail로"는 gmail_send만, "이메일로"는 email_send만 보존(채널 혼선 방지). send-cue는
# "에서"(source)와 안 겹치는 도착 토큰만(예 "리니어에 등록된"=source에 안 걸리게 bare "…에 등록" 금지).
_SLACK_SEND = (
    "슬랙으로", "슬랙 으로", "슬랙에 보내", "슬랙에 올려", "슬랙에 게시", "슬랙에 전송",
    "슬랙 알림", "슬랙으로 알림", "슬랙 채널로", "슬랙 채널에 보내", "슬랙에다", "슬랙에 던",
)
_DUAL_ROLE_SUPPRESS: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    ("gmail_read", (
        ("gmail_send", (
            "gmail로", "gmail 로", "gmail으로", "지메일로", "gmail에 보내", "gmail로 회신",
            "gmail로 발송", "gmail로 전송", "gmail에 회신", "지메일에 보내",
        )),
        ("email_send", (
            "이메일로", "이메일 보내", "이메일로 보내", "이메일로 발송", "이메일로 전송",
            "이메일에 보내", "메일로 보내", "메일로 발송", "메일로 전송", "메일로 회신",
        )),
    )),
    ("slack_read", (("slack_post_message", _SLACK_SEND), ("slack_notify", _SLACK_SEND))),
    ("linear_read", (("linear_create_issue", (
        "리니어로", "리니어에 새", "리니어 이슈 생성", "리니어에 티켓 생성", "리니어에 만들",
        "리니어에 추가", "리니어에 생성", "리니어로 등록",
    )),)),
    ("google_docs_read", (("google_docs_write", (
        "문서로 저장", "문서에 저장", "닥스에 저장", "문서로 기록", "문서로 써", "구글독스로",
        "구글 docs로", "docs에 저장", "문서로 만들", "닥스로",
    )),)),
    ("google_calendar_read", (("google_calendar_create_event", (
        "일정 등록", "일정 추가", "일정 잡", "캘린더에 등록", "캘린더에 추가", "캘린더로",
        "캘린더에 새", "캘린더에 일정",
    )),)),
)


def suppressed_sink_variants(text: str, sources: tuple[str, ...]) -> set[str]:
    """read-service가 source인데 해당 write의 send-cue가 발화에 없으면 그 write를 억제 대상으로.

    렉시컬 추출(`_suppress_source_bleed`)과 앙상블 resolver(semantic 표까지 차단)가 공유 —
    한 곳에서 방향성 규칙을 정의(drift 방지). ``text``는 소문자화된 발화.
    """
    src_set = set(sources)
    drop: set[str] = set()
    for read_node, writes in _DUAL_ROLE_SUPPRESS:
        if read_node not in src_set:
            continue
        for write_node, send_cues in writes:
            if not any(cue in text for cue in send_cues):
                drop.add(write_node)
    return drop


def _suppress_source_bleed(
    text: str, sources: tuple[str, ...], sinks: tuple[str, ...]
) -> tuple[str, ...]:
    """read-service가 source인데 send-cue 부재면 그 write-variant를 sink에서 제거(방향성)."""
    drop = suppressed_sink_variants(text, sources)
    return tuple(s for s in sinks if s not in drop)

# ── 게이트(검증 루프 함의) ──────────────────────────────────────────────────
_GATE_KEYWORDS: tuple[str, ...] = (
    "통과할 때까지", "만족할 때까지", "기준에 맞을 때까지", "기준 충족", "통과 못하면", "통과 못 하면",
    "검증", "검수", "품질", "재생성", "반복 개선", "개선해서", "점수가", "퀄리티", "기준 미달", "점수 미달",
)

# ── 미지원 shape 신호 (현 라이브러리=선형/루프만) ─────────────────────────────
# 잡히면 조립기가 LLM으로 bail — 억지 선형 납작화 방지. 향후 branch/fan_out 스켈레톤이
# 생기면 라우팅 신호로 승격(ADR-0026 §6.6 확장). 과활성을 피해 분기/병렬을 명확히 가리키는
# 구절만 둔다(예: 단독 "면"은 "하면/되면" 등 빈출이라 금지, "아니면"처럼 양자택일만).
_BRANCH_KEYWORDS: tuple[str, ...] = (
    "아니면", "아니라면", "그렇지 않으면", "그 외에는", "경우에 따라", "에 따라 다르",
    "분기", "조건에 따라", "라면 ", "이라면 ", "유형에 따라", "등급에 따라", "분류에 따라",
)
_FANOUT_KEYWORDS: tuple[str, ...] = (
    "각각", "각 항목", "항목마다", "항목별", "그룹별", "건마다", "건별", "개별적으로",
    "전부 각", "하나하나", "병렬", "목록의 각", "리스트의 각", "각 행", "행마다", "각 건",
)
_RETRY_KEYWORDS: tuple[str, ...] = (
    "재시도", "실패하면", "실패 시", "실패하면 다시", "안 되면 다시", "다시 시도",
    "될 때까지 재시도", "오류 나면", "에러 나면", "실패할 경우", "오류 시",
)
_APPROVAL_KEYWORDS: tuple[str, ...] = (
    "승인", "검토 후", "컨펌", "결재", "허가", "승인되면", "승인받아", "결재 후",
    "승인 후", "승인 요청", "재가",
)
# 단일 가드 조건문(conditional_action) — 임계/비교 가드. "넘으면 경보"처럼 분류·승인 아닌
# 1-action 조건. 빈출 부분문자열("~면" 단독) 과활성을 피해 **비교어가 명시된 토큰만** 둔다
# (skeleton-regressor-fix RC2). 양자택일("아니면")은 has_branch가, 승인은 has_approval가 우선
# 포섭하므로(조립기 라우팅) 여기엔 순수 임계/비교 가드만.
_GUARD_KEYWORDS: tuple[str, ...] = (
    "넘으면", "넘어가면", "넘어서면", "초과하면", "초과 시", "초과되면",
    "이상이면", "이상일 때", "이하이면", "이하일 때", "미만이면", "미만일 때",
    "보다 크면", "보다 작으면", "보다 높으면", "보다 낮으면",
    "도달하면", "임계치", "임계값", "기준치를 넘", "기준을 초과",
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
        sources = _match_ordered(text, _SOURCE_RULES)
        # "드라이브 파일 읽어서"는 google_drive_read인데 "파일 읽" 부분문자열이 generic file_read도
        # 켠다. 더 구체적인 google_drive_read가 있으면 generic file_read를 떨어 과추출 1노드를 막는다
        # (gmail↔email 중복제거와 동일 패턴 — 짧은 토큰 과활성 완화, 리뷰 LOW #2).
        if "google_drive_read" in sources and "file_read" in sources:
            sources = tuple(s for s in sources if s != "file_read")
        sinks = _match_ordered(text, _SINK_RULES)
        # 방향성 소스-블리드 차단 — read-service의 write-variant를 send-cue 부재 시 sink에서 제거
        # (gmail/email dedup **전**: "gmail에서 읽고 이메일로"에서 gmail_send 먼저 떨궈야 email 보존).
        sinks = _suppress_source_bleed(text, sources, sinks)
        # gmail과 generic email이 동시 매칭되면 더 구체적인 gmail_send만 남긴다(중복 채널 방지).
        if "gmail_send" in sinks and "email_send" in sinks:
            sinks = tuple(s for s in sinks if s != "email_send")
        return ExtractedEntities(
            trigger=_match_single(text, _TRIGGER_RULES),
            sources=sources,
            transforms=_match_ordered(text, _TRANSFORM_RULES),
            sinks=sinks,
            needs_gate=any(kw in text for kw in _GATE_KEYWORDS),
            has_branch=any(kw in text for kw in _BRANCH_KEYWORDS),
            has_fanout=any(kw in text for kw in _FANOUT_KEYWORDS),
            has_retry=any(kw in text for kw in _RETRY_KEYWORDS),
            has_approval=any(kw in text for kw in _APPROVAL_KEYWORDS),
            has_guard=any(kw in text for kw in _GUARD_KEYWORDS),
        )
