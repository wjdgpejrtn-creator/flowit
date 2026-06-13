"""카테고리별 고품질 few-shot 레퍼런스 — 모델이 모방하는 '천장'.

단일 환불-Slack 예시만 있으면 모든 스킬이 알림/action 형태로 수렴한다. `meta.category`로 도메인에
맞는 예시를 골라 넣어 편향을 줄인다(토큰 비용은 예시 1개로 동일). 두 종류:
  - 문서 작성(document): ai/output/transform — 가장 흔한 use case. Anthropic 공개 스킬
    `doc-coauthoring`(독자·목적·템플릿 우선 → 섹션별 구성 → 독자 검증)과 `brand-guidelines`(타이포·
    서식 위계)의 전문가 원칙을 9섹션 런북으로 녹였다.
  - 알림/연동(action): action/integration/condition/trigger/utility — 환불→Slack 알림(외부 호출·분기).

composer_instructions의 node_type은 전부 실제 카탈로그(EXECUTABLE_NODE_TYPES)에 존재해야 한다
(환각 차단) — 두 예시 모두 실노드만 참조한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Exemplar:
    """한 few-shot 레퍼런스 — Call A(구조)/Call B(지침서) 프롬프트가 공유."""

    input_meta: dict[str, Any]
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    required_connections: list[str]
    service_type: str | None
    composer_instructions: str
    instructions: str
    families: frozenset[str] = field(default_factory=frozenset)


# ── 문서 작성(document) — doc-coauthoring + brand-guidelines 원칙 반영 ──────────────
_DOCUMENT = Exemplar(
    families=frozenset({"ai", "output", "transform"}),
    input_meta={
        "node_type": "weekly_report_compose",
        "name": "주간 업무 보고서 작성",
        "description": (
            "주간 업무 데이터가 모였을 때 사용. 성과·이슈·다음 주 계획을 독자에 맞춰 표준 양식으로 "
            "구조화한 보고서 초안을 작성한다"
        ),
        "category": "ai",
        "risk_level": "Low",
    },
    inputs={
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "description": "보고 대상 기간(ISO week 또는 날짜 범위). 예: '2026-W24' 또는 '2026-06-08~06-12'",
            },
            "audience": {
                "type": "string",
                "enum": ["경영진", "팀", "고객"],
                "default": "팀",
                "description": "주 독자. 강조점·문체·상세도를 결정한다(doc-coauthoring: 독자·목적 우선)",
            },
            "achievements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "이번 주 핵심 성과 목록(데이터 그대로). 예: ['검색 응답속도 30% 개선']",
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "이슈·리스크 목록(없으면 빈 배열). 예: ['BGE-M3 비용 초과 우려']",
            },
            "next_plan": {
                "type": "array",
                "items": {"type": "string"},
                "description": "다음 주 계획·실행 항목. 예: ['A/B 테스트 종료 및 결과 정리']",
            },
            "tone": {
                "type": "string",
                "enum": ["공식", "간결", "친근"],
                "default": "공식",
                "description": "문체",
            },
            "template_url": {
                "type": "string",
                "description": "(선택) 따라야 할 사내 보고 양식 문서 URL. 있으면 그 섹션 구조를 따른다",
            },
        },
        "required": ["period", "achievements", "next_plan"],
    },
    outputs={
        "type": "object",
        "properties": {
            "report_markdown": {
                "type": "string",
                "description": "완성된 보고서 본문(markdown, 서식 위계 포함)",
            },
            "summary": {
                "type": "string",
                "description": "맨 앞 3줄 핵심 요약(경영진이 첫 화면에서 파악)",
            },
        },
    },
    required_connections=[],
    service_type=None,
    composer_instructions=(
        "## 필수 노드\n이 스킬을 워크플로우에 쓰려면 다음을 순서대로 배치한다:\n"
        "1. `google_sheets_read` 또는 `http_request` (category=action) — 주간 업무 데이터(성과·이슈·계획)를 수집한다.\n"
        "2. `weekly_report_compose` (category=ai) — 수집 데이터를 독자에 맞춰 보고서로 작성한다.\n"
        "3. `google_docs_write` 또는 `pdf_generate` (category=output) — 산출된 보고서를 문서로 저장·배포한다.\n"
        "## 연결\n"
        "- 데이터 소스의 행/응답 → `weekly_report_compose`의 achievements·issues·next_plan 입력으로 매핑한다.\n"
        "- `weekly_report_compose`의 `report_markdown` 출력 → "
        "`google_docs_write`(또는 `pdf_generate`)의 본문 입력으로 연결한다."
    ),
    instructions=(
        "# 주간 업무 보고서 작성\n"
        "## 목적\n한 주의 업무를 독자(경영진/팀)가 빠르게 파악하도록 성과·이슈·다음 주 계획을 "
        "표준 양식으로 구조화해 신뢰할 수 있는 보고서 초안을 만든다.\n"
        "## 언제 사용하나\n주간 보고 주기에 업무 데이터(성과·이슈·계획)가 모였을 때 사용한다. "
        "사용 금지: 데이터가 확정되지 않은 시점, 개인 인사평가 문서.\n"
        "## 사전 조건\n- 입력: period·achievements·next_plan(필수), audience·tone·template_url(선택)\n"
        "- 외부 연결: 없음(원천 데이터는 상위 노드가 공급)\n- 권한: 보고서 텍스트 생성 권한\n"
        "## 처리 절차\n"
        "1. audience와 목적을 먼저 확인해 강조점을 정한다(경영진=의사결정 포인트·리스크, 팀=실행 항목·담당·기한).\n"
        "2. template_url이 있으면 그 양식의 섹션 구조·제목을 그대로 따른다. "
        "없으면 기본 4섹션(요약/성과/이슈·리스크/다음 주 계획)을 쓴다.\n"
        "3. 각 섹션을 입력 데이터에 근거해 작성한다 — 수치·고유명사를 바꾸거나 없는 내용을 지어내지 않는다.\n"
        "4. 서식 위계를 적용한다 — 문서 제목 H1, 섹션 H2, 항목 불릿, 핵심 수치는 굵게(가독성·일관성).\n"
        "5. 맨 앞에 3줄 핵심 요약(summary)을 배치한다(독자가 첫 화면에서 파악하도록).\n"
        "6. 독자 검증: 맥락 없는 사람이 읽어도 약어·내부 코드명이 풀려 있는지 점검하고 마무리한다.\n"
        "## 판단 규칙\n"
        "- audience == '경영진' → 요약·의사결정 필요 항목·리스크를 상단에, 세부 실행은 축약한다.\n"
        "- audience == '팀' → 실행 항목에 담당·기한을 구체적으로 적는다.\n"
        "- issues가 빈 배열 → 이슈 섹션을 생략하지 말고 '특이사항 없음'으로 명시한다.\n"
        "- tone(공식/간결/친근)에 맞춰 문체를 적용한다.\n"
        "## 입력/출력\n입력: period(기간), audience(독자), achievements(성과), issues(이슈), "
        "next_plan(계획), tone(문체), template_url(양식) / 출력: report_markdown(본문), summary(3줄 요약)\n"
        "## 예시\n"
        "- 정상(팀): {period:'2026-W24', audience:'팀', achievements:['검색 응답 30% 개선'], "
        "next_plan:['A/B 테스트 종료']} → H1 제목 + 3줄 요약 + 성과/이슈/계획 섹션, 실행 항목에 담당·기한 포함.\n"
        "- 엣지(경영진·이슈 없음): audience='경영진', issues=[] → "
        "요약·리스크를 상단 배치, 이슈 섹션은 '특이사항 없음'.\n"
        "- 엣지(템플릿 지정): template_url 제공 → 해당 양식의 섹션 구조·제목을 그대로 따른다.\n"
        "## 제약·주의\n"
        "- 입력에 없는 성과·수치를 지어내지 않는다(환각 금지) — 모든 문장은 입력 데이터에 근거할 것.\n"
        "- 약어·내부 코드명은 첫 등장 시 풀어 쓴다(맥락 없는 독자도 이해 가능하게).\n"
        "- 미공개 수치·개인정보가 독자 범위를 벗어나면 제외한다.\n"
        "- 길이는 1페이지 내를 권장하고 요약은 3줄로 고정한다."
    ),
)

# ── 알림/연동(action) — 외부 호출·분기. 기본값(document 외 전 카테고리) ───────────────
_ACTION = Exemplar(
    families=frozenset({"action", "integration", "condition", "trigger", "utility"}),
    input_meta={
        "node_type": "refund_request_slack_alert",
        "name": "환불 요청 매니저 알림",
        "description": "환불·반품 요청이 접수됐을 때 사용. 요청 핵심을 정규화해 담당 매니저 채널에 통보한다",
        "category": "action",
        "risk_level": "Medium",
    },
    inputs={
        "type": "object",
        "properties": {
            "refund_id": {
                "type": "string",
                "description": "환불 요청 건의 고유 ID. 중복 발송 방지 멱등키로도 쓰인다. 예: 'RF-10293'",
            },
            "amount": {"type": "integer", "description": "환불 금액(KRW 정수). 예: 35000"},
            "reason": {
                "type": "string",
                "enum": ["defective", "wrong_item", "change_of_mind"],
                "description": "환불 사유 코드. defective=불량, wrong_item=오배송, change_of_mind=단순변심",
            },
            "customer_name": {
                "type": "string",
                "description": "고객 표시명. PII이므로 메시지에는 마스킹해 노출. 예: '김**'",
            },
            "channel": {
                "type": "string",
                "default": "#cs-refund",
                "description": "통보할 Slack 채널. 미지정 시 '#cs-refund'",
            },
            "requested_at": {
                "type": "string",
                "format": "date-time",
                "description": (
                    "요청 시각(ISO 8601). 단순변심 7일 경과 판단에 사용. 예: '2026-06-13T09:30:00+09:00'"
                ),
            },
        },
        "required": ["refund_id", "amount", "reason"],
    },
    outputs={
        "type": "object",
        "properties": {
            "message_ts": {
                "type": "string",
                "description": "발송된 Slack 메시지 타임스탬프(후속 스레드 참조용). 예: '1718241000.123456'",
            },
            "require_approval": {
                "type": "boolean",
                "description": "금액 임계 초과 등으로 매니저 승인이 필요한 건인지",
            },
            "skipped": {
                "type": "boolean",
                "description": "동일 refund_id로 이미 통보돼 발송을 건너뛰었는지",
            },
        },
    },
    required_connections=["slack"],
    service_type="slack",
    composer_instructions=(
        "## 필수 노드\n이 스킬을 워크플로우에 쓰려면 다음을 순서대로 배치한다:\n"
        "1. `webhook_trigger` (category=trigger) — "
        "환불 요청 폼/웹훅에서 refund_id·amount·reason을 수신한다.\n"
        "2. `if_condition` (category=condition) — amount > 50000 으로 승인 필요 여부를 가른다.\n"
        "3. `slack_post_message` (category=action, service=slack) — 매니저 채널에 통보한다.\n"
        "## 연결\n- `webhook_trigger`의 refund_id·amount·reason → `if_condition` 입력.\n"
        "- `if_condition`의 분기 결과 + 트리거 데이터 → `slack_post_message` 입력.\n"
        "- 고액(true) 경로의 메시지에는 승인 버튼을 포함하도록 구성한다."
    ),
    instructions=(
        "# 환불 요청 매니저 알림\n"
        "## 목적\n환불·반품 요청이 접수되는 즉시 담당 매니저가 SLA 안에 인지·판단하도록, 요청 핵심을 "
        "정규화해 지정 Slack 채널에 통보한다.\n"
        "## 언제 사용하나\n환불·반품 요청 폼 또는 이메일이 접수됐을 때 사용한다. 사용 금지: 단순 배송 조회·"
        "교환 문의(별도 흐름), 이미 통보된 동일 refund_id의 재요청.\n"
        "## 사전 조건\n- 입력: refund_id·amount·reason(필수), customer_name·channel·requested_at(선택)\n"
        "- 외부 연결: slack(chat:write 스코프)\n- 권한: 대상 채널에 봇이 초대돼 게시 가능해야 함\n"
        "## 처리 절차\n"
        "1. refund_id로 기존 통보 여부를 조회한다 — 이미 통보됐으면 skipped=true로 즉시 종료한다.\n"
        "2. amount를 KRW 정수로 정규화하고 reason을 사유 코드로 검증한다.\n"
        "3. 판단 규칙으로 require_approval을 산출한다.\n"
        "4. Slack Block Kit 메시지를 구성한다 — 헤더(요청ID·금액), 본문(사유·마스킹 고객명·요청시각), "
        "require_approval이면 '매니저 승인 필요' 배지와 [승인]/[반려] 버튼을 추가한다.\n"
        "5. channel(미지정 시 '#cs-refund')에 chat.postMessage로 발송하고 "
        "반환된 ts를 message_ts에 기록한다.\n"
        "## 판단 규칙\n"
        "- amount > 50000 → require_approval=true('매니저 승인 필요' 배지+버튼).\n"
        "- amount ≤ 50000 → require_approval=false('자동 처리 가능' 표기).\n"
        "- reason=change_of_mind 이고 requested_at이 구매 후 7일 초과 → "
        "본문에 '환불 정책 위반 가능' 경고를 덧붙인다.\n"
        "## 입력/출력\n입력: refund_id(멱등키), amount(원), reason(사유 코드), customer_name(마스킹), "
        "channel, requested_at / 출력: message_ts, require_approval, skipped\n"
        "## 예시\n"
        "- 정상: {refund_id:'RF-10293', amount:35000, reason:'defective'} → '자동 처리 가능' 메시지 발송, "
        "{message_ts:'1718241000.123456', require_approval:false, skipped:false}\n"
        "- 엣지(고액): amount=120000 → '매니저 승인 필요' 배지+버튼 포함 발송, require_approval=true\n"
        "- 엣지(중복): 동일 refund_id 재요청 → 발송 안 함, {skipped:true}\n"
        "## 제약·주의\n"
        "- 고객 이메일·전화·전체 실명은 PII — 메시지 본문 평문 노출 금지(이름은 마스킹, 연락처는 제외).\n"
        "- 금액은 KRW 정수, 시각은 ISO 8601로 표기한다.\n"
        "- refund_id를 멱등키로 사용해 중복 발송을 막는다.\n"
        "- 발송 실패 시 1회 재시도하고, 그래도 실패하면 '#cs-ops' 채널로 에스컬레이션한다."
    ),
)

_EXEMPLARS = (_DOCUMENT, _ACTION)


def select_fewshot(category: str) -> Exemplar:
    """meta.category에 맞는 few-shot 레퍼런스 선택. 매칭 없으면 action(기본)."""
    for ex in _EXEMPLARS:
        if category in ex.families:
            return ex
    return _ACTION


def structured_fewshot(ex: Exemplar) -> dict[str, Any]:
    """Call A(구조 추출) 프롬프트용 few-shot dict."""
    return {
        "input_meta": ex.input_meta,
        "expected_output": {
            "inputs": ex.inputs,
            "outputs": ex.outputs,
            "required_connections": ex.required_connections,
            "service_type": ex.service_type,
            "composer_instructions": ex.composer_instructions,
        },
    }


def instructions_fewshot(ex: Exemplar) -> dict[str, Any]:
    """Call B(SKILL.md 추출) 프롬프트용 few-shot dict."""
    return {
        "input_meta": ex.input_meta,
        "expected_output": {"instructions": ex.instructions},
    }
