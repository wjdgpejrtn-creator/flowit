"""스킬빌더 instructions 품질 A/B 테스트 — Gemma(llm-base)가 Anthropic Claude Skill 형식을
실제로 뽑는지 검증. 빌더 코드/Modal 재배포 없이 llm-base를 직접 호출.

before(현행 3섹션) vs after(9섹션+trigger description)를 같은 HR 노드·SOP로 각각 생성해
출력을 나란히 출력한다. 형식 준수·description trigger 여부를 사람이 판정 → 조장 제안 근거.

실행: LLM_BASE_URL=<llm-base /v1/generate 호스트> .venv\\Scripts\\python scripts/test_skill_instructions_quality.py
필요 env: LLM_BASE_URL (shell env로 주입 — .env 파싱하지 않음, CLAUDE.md 보안 규칙 정합)
"""
# ruff: noqa: E501  — 테스트 데이터(긴 한국어 프롬프트/SOP 문자열) 가독성 위해 줄길이 예외
from __future__ import annotations

import json
import os
import sys

import httpx

_MAX_TOKENS = 8192

# ── 공통 입력: 테스트 대상 노드 메타 + SOP 문서 컨텍스트 ─────────────────────────
TARGET_META = {
    "node_type": "hr_onboarding_workflow",
    "name": "신규 입사자 온보딩 안내문 자동 작성",
    "description": "신규 입사자 정보로 온보딩 안내문 작성",
    "category": "action",
    "risk_level": "Medium",
}

# 사용자가 업로드할 법한 '현실적으로 얕은' 온보딩 SOP — Gemma가 이걸 근거로 깊은 런북을
# 구조화해낼 수 있는지가 핵심 검증 포인트.
SOP_DOCUMENT = {
    "file_name": "신규입사자_온보딩_SOP.docx",
    "blocks": [
        {"block_type": "heading", "text": "신규 입사자 온보딩 절차"},
        {"block_type": "text", "text": "입사 확정 시 인사팀은 부서·직무·입사일을 확인한다."},
        {"block_type": "text", "text": "1. 첫날 안내: 출근 시간(09:30)·장소(본사 3층), 신분증·통장사본 지참."},
        {"block_type": "text", "text": "2. 계정 발급: 회사 이메일, 그룹웨어, 직무별 시스템(개발은 코드저장소·CI 포함)."},
        {"block_type": "text", "text": "3. 제출 서류: 근로계약서, 비밀유지서약서 — 입사 후 3일 내 인사팀 제출."},
        {"block_type": "text", "text": "4. 필수 교육: 정보보안 교육(입사 1주 내 이수)."},
        {"block_type": "text", "text": "5. 담당자: 인사 담당, 직속 매니저, 멘토(미지정 시 추후 배정)."},
    ],
}

# ── before: 현행 3섹션 instruction (build_from_sop_use_case.py 534-541 발췌) ──────
INSTRUCTION_OLD = (
    "당신은 SOP 문서에서 추출된 SkillNode의 상세 스펙을 채우는 어시스턴트입니다. "
    "target_skill_meta 노드에 대해 SOP를 근거로 두 필드를 생성하세요:\n"
    "  - description: 노드 동작 설명 (한 문장)\n"
    "  - instructions: 이 스킬의 SKILL.md 본문 (markdown). 사용자가 읽고 선택할 수 있도록 "
    "'## When to use', '## Steps', '## Inputs/Outputs' 섹션을 포함한 충분한 설명.\n"
    "출력은 반드시 JSON. instructions 값은 markdown 문자열."
)

# ── after: 업그레이드 9섹션 + trigger 중심 description ──────────────────────────
INSTRUCTION_NEW = (
    "당신은 SOP 문서의 작업을 Anthropic Claude Skill 수준의 스킬 지침서로 작성하는 "
    "어시스턴트입니다. target_skill_meta 노드에 대해 SOP를 근거로 두 필드를 생성하세요:\n\n"
    "  - description: 이 스킬을 **언제 호출해야 하는가**를 1~2문장으로. '무엇을 하는 스킬인지' + "
    "'어떤 상황/요청일 때 쓰는지(트리거)'를 모두 담는다. 모델이 이 한 줄만 보고 스킬 선택을 "
    "판단하므로 트리거가 구체적이어야 한다. (예: '...할 때 사용')\n\n"
    "  - instructions: SKILL.md 본문 (markdown). 모델이 읽고 그대로 실행할 수 있는 런북이며 "
    "다음 9개 섹션을 **모두** 포함한다:\n"
    "    1. (첫 줄) `# {스킬명}`\n"
    "    2. `## 목적`\n"
    "    3. `## 언제 사용하나` (쓰면 안 되는 경우도 1줄)\n"
    "    4. `## 사전 조건` (필요 입력·외부 연결·권한)\n"
    "    5. `## 처리 절차` (명령형 번호 단계, 각 단계 동사로 시작, 추상어 금지)\n"
    "    6. `## 판단 규칙` (분기·승인·예외의 구체 조건/임계값)\n"
    "    7. `## 입력/출력` (필드별 의미)\n"
    "    8. `## 예시` (정상 1 + 엣지 1~2, 입력→기대 행동)\n"
    "    9. `## 제약·주의` (형식·민감정보·실패 시 행동)\n"
    "  작성 원칙: (a) 비전문가가 따라 할 수 있게 구체적으로 (b) '적절히/알아서' 같은 모호어 금지 "
    "(c) SOP에 수치·규칙이 있으면 그대로 인용 (d) 한국어.\n\n"
    "출력은 반드시 JSON. instructions 값은 사람이 읽는 markdown 문자열."
)

# after용 Anthropic급 few-shot (환불 알림 예시를 9섹션으로)
FEW_SHOT_NEW = {
    "input_meta": {"node_type": "refund_request_slack_alert", "name": "환불 요청 매니저 알림",
                   "category": "action", "risk_level": "Medium"},
    "expected_output": {
        "description": "환불 요청이 접수되어 담당 매니저에게 즉시 알려야 할 때 사용. 요청 정보를 요약해 지정 Slack 채널로 통보한다.",
        "instructions": (
            "# 환불 요청 매니저 알림\n"
            "## 목적\n환불 요청 접수 시 매니저가 빠르게 인지·대응하도록 자동 통보한다.\n"
            "## 언제 사용하나\n환불 요청 폼이 접수됐을 때. 단순 문의는 대상 아님.\n"
            "## 사전 조건\n입력: 환불 ID·금액·채널 / 연결: slack\n"
            "## 처리 절차\n1. 요청 정보를 확인한다. 2. 금액·사유를 한 줄로 요약한다. 3. 지정 채널에 발송한다.\n"
            "## 판단 규칙\n금액이 5만원 초과면 메시지에 '승인 필요'를 표기한다.\n"
            "## 입력/출력\n입력: refund_id, amount, channel / 출력: message_ts\n"
            "## 예시\n정상: 3.5만원 → 채널 통보. 엣지: 10만원 → '승인 필요' 표기.\n"
            "## 제약·주의\n사유에 민감정보가 있으면 원문 노출 금지, 분류만 표기한다."
        ),
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"description": {"type": "string"}, "instructions": {"type": "string"}},
    "required": ["description", "instructions"],
}


# ── 굳히기 케이스 2: 분기(condition) 노드 + 슬랙 — 휴가 승인 ─────────────────────
META_PTO = {
    "node_type": "hr_pto_request",
    "name": "휴가 신청 승인",
    "description": "휴가 신청을 종류별로 분류해 승인 판단 후 캘린더 등록·알림",
    "category": "condition",
    "risk_level": "Medium",
}
SOP_PTO = {
    "file_name": "휴가신청_처리_SOP.docx",
    "blocks": [
        {"block_type": "heading", "text": "휴가 신청 처리 절차"},
        {"block_type": "text", "text": "직원이 휴가 신청서를 제출하면 종류(연차/반차/병가)를 확인한다."},
        {"block_type": "text", "text": "잔여 연차가 신청 일수보다 적으면 반려한다."},
        {"block_type": "text", "text": "연차·반차는 매니저 승인 후 팀 구글 캘린더에 등록한다."},
        {"block_type": "text", "text": "병가는 사전 승인 없이 인사팀과 매니저에게 슬랙으로 통보한다."},
    ],
}

# ── 굳히기 케이스 3: 다른 도메인(이커머스) + 일부러 얕고 지저분한 한 줄 SOP ────────
META_REFUND = {
    "node_type": "ecommerce_refund_approval",
    "name": "환불 승인 처리",
    "description": "환불 요청 금액 기준 자동/수동 승인 분기",
    "category": "condition",
    "risk_level": "High",
}
SOP_REFUND = {
    "file_name": "환불정책_메모.txt",
    "blocks": [
        {"block_type": "text", "text": "환불요청들어오면 5만원 넘으면 매니저 승인받고 아니면 그냥 자동승인. 슬랙으로 알려주고."},
    ],
}


def build_prompt(instruction: str, few_shot: dict | None, meta: dict, doc: dict) -> str:
    payload = {
        "instruction": instruction,
        "document": doc,
        "target_skill_meta": meta,
        "output_schema": OUTPUT_SCHEMA,
    }
    if few_shot:
        payload["few_shot_example"] = few_shot
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run(label: str, instruction: str, few_shot: dict | None, meta: dict, doc: dict) -> None:
    prompt = build_prompt(instruction, few_shot, meta, doc)
    augmented = prompt + "\n\n위 output_schema에 맞는 JSON 객체만 반환하세요. 마크다운 없이 JSON만 출력하세요."
    base = os.environ["LLM_BASE_URL"].rstrip("/")
    resp = httpx.post(
        f"{base}/v1/generate",
        json={"prompt": augmented, "max_tokens": _MAX_TOKENS, "format": "json", "json_schema": OUTPUT_SCHEMA},
        timeout=300.0,
    )
    resp.raise_for_status()
    raw = str(resp.json().get("generated_text", "")).strip()
    print("\n" + "=" * 80 + f"\n[{label}]\n" + "=" * 80)
    try:
        obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        print("\n--- description ---\n" + obj.get("description", "(없음)"))
        print("\n--- instructions (SKILL.md body) ---\n" + obj.get("instructions", "(없음)"))
    except Exception as e:
        print(f"[파싱 실패: {e}]\n원문:\n{raw[:2000]}")


if __name__ == "__main__":
    if not os.getenv("LLM_BASE_URL"):
        sys.exit(
            "LLM_BASE_URL 미설정 — shell env로 llm-base /v1/generate 호스트를 주입하세요. "
            "예: LLM_BASE_URL=https://<host> .venv\\Scripts\\python scripts/test_skill_instructions_quality.py"
        )
    # CASE1: 동일 입력(온보딩)에 instruction만 BEFORE(3섹션) vs AFTER(9섹션+trigger) — 핵심 A/B
    run("CASE1 BEFORE — 온보딩 · 현행 3섹션", INSTRUCTION_OLD, None, TARGET_META, SOP_DOCUMENT)
    run("CASE1 AFTER — 온보딩 · 9섹션 + trigger description", INSTRUCTION_NEW, FEW_SHOT_NEW, TARGET_META, SOP_DOCUMENT)
    # 굳히기 — AFTER(9섹션)가 노드 종류·도메인·문서 품질이 달라도 형식을 유지하나
    run("CASE2 AFTER — 휴가 승인 (분기 condition + 슬랙)", INSTRUCTION_NEW, FEW_SHOT_NEW, META_PTO, SOP_PTO)
    run("CASE3 AFTER — 이커머스 환불 승인 (다른 도메인 + 얕고 지저분한 한 줄 SOP)",
        INSTRUCTION_NEW, FEW_SHOT_NEW, META_REFUND, SOP_REFUND)
