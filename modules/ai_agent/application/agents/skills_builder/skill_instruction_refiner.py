"""SKILL.md 지침서 품질 자기개선 루프 — draft → 비평(critique) → 재작성(refine).

문제: Gemma(llm-base)는 작은 모델이라 1샷으로는 "초등학생 끄적임" 수준의 얕은 지침서를
뱉는다. 프롬프트를 9섹션 루브릭으로 고도화해도 단일 호출 품질은 들쭉날쭉하다.

해법(ADR-0028 후속, composer qa_evaluator 패턴 이식): 초안을 받은 뒤 같은 모델에게
**자기 산출물을 루브릭으로 채점·결함 지적(critique)** 시키고, 그 비평을 반영해
**재작성(refine)** 시킨다. 구조적으로 얕은 초안을 모델이 스스로 끌어올린다.

비용/안전:
- 추가 LLM 호출 2회(critique + refine). 추출 detail 단계에 한정(메타 단계는 불변).
- **graceful**: critique/refine 어느 단계가 실패하거나 형태 불일치면 초안을 그대로 반환한다
  (품질 보강은 best-effort, 추출 자체를 깨지 않음).
- **8192 ctx 방어**: refine 입력은 SOP 본문을 다시 넣지 않고 (meta + 초안 + 비평)만 — 초안은
  문서 사실을 이미 담았으므로 refine은 '구조·품질 개선'에 집중한다. 초안이 비정상적으로 길면
  입력용으로만 절단(원본 fallback 값은 보존).
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

from ....domain.ports.llm_port import LLMPort

_logger = logging.getLogger(__name__)

# refine 입력에 실을 초안 최대 길이(char). 8192 ctx에 (초안+비평+루브릭+출력)이 함께 들어가야
# 하므로 초안 입력을 보수적으로 제한한다(detail 초안 instructions는 통상 이보다 짧음 — 방어선).
_MAX_DRAFT_CHARS_FOR_REFINE = 6000
_CRITIQUE_MAX_TOKENS = 1100
_REFINE_MAX_TOKENS = 3200

# 고품질 SKILL.md 9섹션 구조 — draft 프롬프트와 refine 프롬프트가 공유하는 SSOT.
# Anthropic Claude Skill 수준의 "모델이 읽고 그대로 실행하는 런북"을 목표로 한다.
SKILL_MD_SECTIONS = (
    "    1. (첫 줄) `# {스킬명}`\n"
    "    2. `## 목적` — 이 스킬이 해결하는 문제 1~2문장\n"
    "    3. `## 언제 사용하나` — 트리거 상황 + 쓰면 안 되는 경우도 1줄\n"
    "    4. `## 사전 조건` — 필요한 입력·외부 연결·권한. **입력마다 그 데이터가 "
    "어디서 오는지(데이터 소스: Google Sheets/이메일/업로드 파일/외부 API/트리거 payload 등)를 "
    "반드시 명시** (예: `sales_data` ← Google Sheets 'daily_sales' 시트)\n"
    "    5. `## 처리 절차` — 명령형 번호 단계(각 단계 동사로 시작, 추상어 금지). "
    "**외부 데이터를 다루는 스킬이면 1단계는 반드시 '지정된 소스에서 원본 데이터를 읽어/가져와 "
    "작업 변수로 둔다'는 데이터 획득 단계**여야 한다 (예: 1. Google Sheets의 지정 범위를 읽어 "
    "`sales_data`로 사용한다). 데이터가 손에 이미 있다고 가정하고 계산부터 시작하지 말 것\n"
    "    6. `## 판단 규칙` — 분기·승인·예외의 구체 조건/임계값(SOP에 수치 있으면 그대로 인용)\n"
    "    7. `## 입력/출력` — 필드별 의미 + 각 입력의 출처(데이터 소스)\n"
    "    8. `## 예시` — 정상 1 + 엣지 1~2 (입력→기대 행동)\n"
    "    9. `## 제약·주의` — 형식·민감정보(PII)·실패 시 행동"
)

# instructions(SKILL.md) 작성 품질 바 — draft 프롬프트 instruction에 주입 + critique 채점 기준.
SKILL_MD_QUALITY_RULES = (
    "작성 원칙: (a) 비전문가가 그대로 따라 할 수 있게 구체적으로 "
    "(b) '적절히/알아서/등등' 같은 모호어 금지 "
    "(c) SOP에 수치·규칙·이름이 있으면 그대로 인용(지어내기 금지) "
    "(d) 처리 절차는 명령형 동사로 시작 (e) 한국어 "
    "(f) 데이터를 소비하는 스킬은 **입력의 출처(데이터 소스)를 명시**하고, 처리 절차 1단계에서 "
    "그 소스(시트/메일/업로드/API 등)로부터 데이터를 읽어 작업 변수에 바인딩할 것 — "
    "데이터가 어디서 오는지 암묵에 맡기지 말 것(소스 미지정 시 LLM이 '메일로 받는다' 등으로 오추론)."
)

# critique가 채점하는 9개 루브릭 차원(각 항목 0~2점). refine이 끌어올릴 결함을 드러낸다.
_RUBRIC_DIMENSIONS = (
    "1. 9개 섹션(# 제목/## 목적/언제 사용하나/사전 조건/처리 절차/판단 규칙/입력·출력/예시/제약·주의)이 모두 있는가",
    "2. 처리 절차가 명령형 동사로 시작하는 구체 단계인가(추상어 없음)",
    "3. 판단 규칙에 구체 조건/임계값이 있고 SOP 수치를 인용했는가",
    "4. 모호어('적절히/알아서/등')가 없는가",
    "5. 예시가 정상 + 엣지를 모두 포함하는가",
    "6. 제약·주의에 형식·민감정보(PII)·실패 시 행동이 있는가",
    "7. 사전 조건에 입력·연결·권한이 명시됐는가",
    "8. SOP에 없는 사실을 지어내지 않았는가(환각 없음)",
    "9. 데이터를 소비하는 스킬이면, 사전 조건에 각 입력의 데이터 소스가 명시되고 처리 절차가 "
    "그 소스에서 데이터를 읽어 작업 변수에 바인딩하는 단계로 시작하는가(입력 출처가 암묵이 아님)",
)


class _RefinedInstructions(BaseModel):
    """refine 호출 structured 출력 — instructions(SKILL.md) 본문 1필드."""

    model_config = ConfigDict(frozen=True)

    instructions: str = Field(min_length=1)


def build_critique_prompt(skill_name: str, draft_instructions: str) -> str:
    """초안 SKILL.md를 9개 루브릭으로 채점·결함 지적시키는 프롬프트(자유 텍스트 응답).

    SOP 본문은 넣지 않는다 — 초안 자체의 구조·구체성·환각을 평가한다(ctx 절약 + 평가 집중).
    """
    rubric = "\n".join(_RUBRIC_DIMENSIONS)
    return (
        f"당신은 업무 자동화 스킬 지침서(SKILL.md)를 심사하는 깐깐한 리뷰어입니다.\n"
        f"아래 '{skill_name}' 스킬의 SKILL.md 초안을 다음 9개 기준으로 각 0~2점 채점하고, "
        f"항목별로 **무엇이 부족한지 + 어떻게 고쳐야 하는지**를 구체적으로 지적하세요. "
        f"두루뭉술한 칭찬 금지 — 실제 결함과 개선 지시만 한국어로.\n\n"
        f"[채점 기준]\n{rubric}\n\n"
        f"[SKILL.md 초안]\n{draft_instructions}\n\n"
        f"출력: 항목별 점수 + 개선 지시 목록(자유 텍스트)."
    )


def build_refine_prompt(skill_name: str, draft_instructions: str, critique: str) -> str:
    """비평을 반영해 SKILL.md를 재작성시키는 프롬프트(structured JSON 응답)."""
    return (
        f"당신은 업무 자동화 스킬 지침서(SKILL.md)를 고쳐 쓰는 전문 작성자입니다.\n"
        f"아래 '{skill_name}' 스킬의 SKILL.md 초안과 리뷰어 비평을 받아, **비평의 모든 지적을 "
        f"반영해** SKILL.md를 완전히 다시 작성하세요.\n\n"
        f"구조는 다음 9섹션을 모두 유지합니다:\n{SKILL_MD_SECTIONS}\n\n"
        f"{SKILL_MD_QUALITY_RULES}\n\n"
        f"[SKILL.md 초안]\n{draft_instructions}\n\n"
        f"[리뷰어 비평]\n{critique}\n\n"
        f"출력은 반드시 JSON 객체 1개 — instructions 필드에 재작성한 SKILL.md markdown 본문만 담으세요."
    )


class SkillInstructionRefiner:
    """SKILL.md 초안을 critique→refine 1패스로 끌어올린다. 실패 시 초안 그대로 반환(graceful)."""

    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def refine(self, skill_name: str, draft_instructions: str) -> str:
        """초안 → 비평 → 재작성. 어느 단계든 실패/형태불일치면 초안을 그대로 반환한다.

        Args:
            skill_name: 스킬 이름(프롬프트 맥락용).
            draft_instructions: 1차 추출이 만든 SKILL.md 초안(markdown).

        Returns:
            재작성된 SKILL.md(성공) 또는 초안(실패 폴백). 빈 초안이면 그대로 반환.
        """
        if not draft_instructions or not draft_instructions.strip():
            return draft_instructions

        # refine 입력용 초안 절단(원본 fallback 값은 보존 — ctx 방어).
        draft_for_input = draft_instructions[:_MAX_DRAFT_CHARS_FOR_REFINE]

        try:
            critique = await self._llm.generate(
                build_critique_prompt(skill_name, draft_for_input),
                max_tokens=_CRITIQUE_MAX_TOKENS,
            )
        except Exception as e:
            _logger.warning("SKILL.md critique 실패(초안 유지) %s: %s", skill_name, e)
            return draft_instructions
        if not isinstance(critique, str) or not critique.strip():
            _logger.warning("SKILL.md critique 빈 응답(초안 유지) %s", skill_name)
            return draft_instructions

        try:
            refined = await self._llm.generate_structured(
                build_refine_prompt(skill_name, draft_for_input, critique[:_MAX_DRAFT_CHARS_FOR_REFINE]),
                _RefinedInstructions,
                max_tokens=_REFINE_MAX_TOKENS,
            )
        except Exception as e:
            _logger.warning("SKILL.md refine 실패(초안 유지) %s: %s", skill_name, e)
            return draft_instructions
        if not isinstance(refined, _RefinedInstructions) or not refined.instructions.strip():
            _logger.warning("SKILL.md refine 형태불일치/빈 응답(초안 유지) %s", skill_name)
            return draft_instructions

        return refined.instructions
