"""Skills Builder — SOP 문서(DocumentBlock) → LLM → wizard extract_draft + confirm (ADR-0020 ③-a).

REQ-004 spec §2.2 BuildFromSOPUseCase. wizard 1차(Q8): 추출 결과를 사용자가 검토·수정 후 확정.

LLM 호출은 LLMPort stub으로 단위 테스트 가능, 실 endpoint(`llm-base` Modal) 배포 후 wiring.

흐름 (2단계 wizard):
    [extract_draft] DocumentBlock + personal_memory(list[MemoryEntry])
      → JSON prompt 구성 (XML 금지 — 메모리 룰)
      → LLM.generate_structured(prompt, ExtractedSkillNodeList)
      → 응답 검증 + NodeSpecStaging 변환 (NodeDefinition 미생성 — Option B)
      → ResultFrame(payload.skills) — 사용자 검토·수정용, **저장 X**
    [confirm] 편집된 skills
      → embed(description) + CreateDraftSkillUseCase로 personal DRAFT 생성
      → ResultFrame(payload.skill_ids). NodeDefinition은 publish 시점(②d)에 생성.

──────────────────────────────────────────────────────────────────────────────
5/16 본격 구현 시 wiring 가이드 (신정혜 ModalLLMAdapter 완성 후)
──────────────────────────────────────────────────────────────────────────────

1) LLMPort 구현체 (신정혜 작업):
   ``modules/ai_agent/adapters/llm/modal_llm_adapter.py`` 의 ``ModalLLMAdapter``가
   ``llm-base`` Modal app을 `modal.Cls.from_name("llm-base", "LLMBase")` RPC로 호출.
   ``generate_structured(prompt, schema)`` 구현 시:
       - ``format="json"`` + ``json_schema=schema.model_json_schema()`` 옵션 전달
       - llm-base가 grammar-level constraint로 JSON 강제 (응답 100% parseable)

2) EmbedderPort 구현체 (신정혜 작업):
   ``modules/ai_agent/adapters/llm/modal_embedding_adapter.py``의 ``ModalEmbeddingAdapter``가
   ``llm-base``의 ``POST /v1/embed`` HTTP endpoint 호출.

3) Composition root (api_server 또는 운영 스크립트) — wizard 1차(ADR-0020 Q8):
   ```python
   from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
   from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
   from skills_marketplace.application.use_cases import CreateDraftSkillUseCase
   from storage.repositories import PgSkillRepository  # 조장 PR-2d (SkillRepository 3-scope 구현)

   use_case = BuildFromSOPUseCase(
       create_draft_skill=CreateDraftSkillUseCase(PgSkillRepository(...)),
       embedder=ModalEmbeddingAdapter(base_url=os.environ["EMBEDDING_BASE_URL"]),
       llm=ModalLLMAdapter(),  # MODAL_TOKEN_ID/SECRET 환경변수 자동 사용
   )
   # 2단계: extract_draft(user_id, document, personal_memory) → 사용자 검토·수정 → confirm(user_id, skills)
   # NodeDefinition은 미생성(Option B) — publish 시점(PublishSkillUseCase ②d)에 staging→NodeDefinition.
   ```

4) Modal app endpoint (박아름 5/17 plan):
   ``services/agents/agent-skills-builder/main.py``에서 ``BuildFromSOPUseCase`` 또는
   ``BuildFromIndustryDefaultUseCase`` 또는 ``BuildFromFunctionalDomainUseCase``를
   라우팅 (AgentProtocolRequest.payload['source_type']로 분기).

5) 프롬프트 튜닝 (실 LLM 응답 보면서):
   ``_build_prompt``의 few-shot 예시 / instruction 문구는 첫 e2e 후 보강.
   샘플 SOP 3종(PDF/DOCX/HWP)으로 응답 품질 측정.
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from common_schemas import DocumentBlock, MemoryEntry
from common_schemas.enums import RiskLevel
from common_schemas.transport import AgentNodeFrame, ErrorFrame, ResultFrame, SSEFrame
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from skills_marketplace.application.use_cases import CreateDraftSkillUseCase
from skills_marketplace.domain.value_objects import NodeSpecStaging

from ....domain.entities.skill_node import SkillNode
from ....domain.ports.llm_port import LLMPort

# DB CHECK 영문 8종 (`009_node_definitions.sql`).
_ALLOWED_CATEGORIES = {"trigger", "action", "condition", "transform", "ai", "integration", "utility", "output"}


# ----------------------------------------------------------------------
# LLM structured response 래퍼
# ----------------------------------------------------------------------


class _ExtractedSkillNode(BaseModel):
    """LLM이 SOP에서 추출한 SkillNode 1건 (BuildFromSOP 내부 표현).

    LLM 응답 검증용 — Pydantic이 자동 validate.
    NodeDefinition 변환 시 추가 메타(node_id/version/parameter_schema/embedding)는 use case가 채움.

    `instructions`는 ADR-0017 이중 저장 중 SkillDocument(SKILL.md) 지침서 본문 —
    LLM이 NodeDefinition 메타와 함께 동시 생성한다 (사용자 대화 중 옵션 제시용 사람이 읽는 형식).
    skills_marketplace.SkillDocument를 직접 import하지 않고 dict 데이터로 반환 (조장 리뷰 #98
    "ai_agent는 use case 경유" 결정 — 저장 wiring은 후속 GCS adapter + skills_marketplace use case).
    """
    model_config = ConfigDict(frozen=True)

    node_type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str                           # 영문 8종 (검증은 use case에서)
    risk_level: str                         # Low/Medium/High/Restricted
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    required_connections: list[str] = Field(default_factory=list)
    service_type: str | None = None
    instructions: str = Field(min_length=1)  # SkillDocument(SKILL.md) markdown body — ADR-0017


class _ExtractedSkillNodeList(BaseModel):
    """LLM structured output 컨테이너."""
    model_config = ConfigDict(frozen=True)

    skill_nodes: list[_ExtractedSkillNode]


# ----------------------------------------------------------------------
# UseCase
# ----------------------------------------------------------------------


class BuildFromSOPUseCase:
    """SOP DocumentBlock → LLM 추출 → wizard extract_draft + confirm (ADR-0020 ③-a, Q8 wizard 1차).

    - extract_draft: 추출 결과(NodeSpecStaging + name/desc/instructions)만 반환, **저장 X** — 사용자 검토·수정용
    - confirm: 편집 결과 → CreateDraftSkillUseCase로 personal DRAFT 생성 (Option B — NodeDefinition은 publish 시점)
    - JSON 강제 (LLM 입출력), category/risk_level 검증
    """

    def __init__(
        self,
        create_draft_skill: CreateDraftSkillUseCase,
        embedder: EmbedderPort,
        llm: LLMPort,
    ) -> None:
        self._create_draft_skill = create_draft_skill
        self._embedder = embedder
        self._llm = llm

    async def extract_draft(
        self,
        user_id: UUID,
        document: DocumentBlock,
        personal_memory: list[MemoryEntry] | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        """wizard 1단계 — SOP에서 SkillNode 추출 → 노드 스펙(staging) + 메타 반환. **저장 안 함**.

        사용자가 추출 결과를 검토·수정한 뒤 `confirm`으로 확정한다 (ADR-0020 Q8 wizard 1차).

        Yields:
            AgentNodeFrame (진행) / ErrorFrame (실패) / ResultFrame(payload.skills) — 추출 결과 목록
        """
        personal_memory = personal_memory or []

        if not document.blocks:
            yield ErrorFrame(
                code="E_DOCUMENT_EMPTY",
                message=f"DocumentBlock(id={document.document_id})에 blocks 없음 — 추출할 내용 없음",
            )
            return

        yield AgentNodeFrame(agent_node_name="skills_builder.sop.parse_document")
        prompt = self._build_prompt(document, personal_memory)
        yield AgentNodeFrame(agent_node_name="skills_builder.sop.llm_extract")

        try:
            extracted = await self._llm.generate_structured(prompt, _ExtractedSkillNodeList)
        except Exception as e:
            yield ErrorFrame(code="E_LLM_GENERATION_FAILED", message=f"LLM 호출 실패: {e}")
            return

        if not isinstance(extracted, _ExtractedSkillNodeList):
            yield ErrorFrame(
                code="E_LLM_RESPONSE_INVALID",
                message=f"LLM 응답이 _ExtractedSkillNodeList 형태 아님: {type(extracted).__name__}",
            )
            return

        if not extracted.skill_nodes:
            yield ErrorFrame(
                code="E_NO_SKILLS_EXTRACTED",
                message="LLM이 SkillNode를 추출하지 못함 (SOP 문서에 자동화 가능 작업 없음으로 판단)",
            )
            return

        # 각 추출 항목 → NodeSpecStaging 변환 (LLM 응답 비유효 시 전체 중단 — fail-fast)
        skills: list[dict] = []
        for ext in extracted.skill_nodes:
            try:
                staging = self._convert_to_staging(ext)
            except (KeyError, ValueError) as e:
                yield ErrorFrame(
                    code="E_LLM_RESPONSE_INVALID",
                    message=f"LLM 추출 항목 변환 실패 ({ext.node_type}): {e}",
                )
                return
            skills.append({
                "node_type": ext.node_type,
                "name": ext.name,
                "description": ext.description,
                "instructions": ext.instructions,  # SKILL.md 본문 — confirm이 GCS 저장(use case 경유)
                "staging": staging.model_dump(mode="json"),
            })

        yield ResultFrame(
            intent="build_skill",
            payload={
                "source_type": "sop",
                "document_id": str(document.document_id),
                "file_name": document.file_meta.file_name,
                "skills": skills,  # 사용자 검토·수정 대상 (저장 전)
                "user_id": str(user_id),
            },
        )

    async def confirm(
        self,
        user_id: UUID,
        skills: list[dict],
    ) -> AsyncGenerator[SSEFrame, None]:
        """wizard 2단계 — 사용자가 편집·확정한 추출 결과 → personal DRAFT 스킬 생성.

        각 skill = `{node_type, name, description, instructions, staging:{...}}` (extract_draft 결과를
        사용자가 편집한 형태). `CreateDraftSkillUseCase`로 DRAFT 생성 (Option B — NodeDefinition은 publish 시).

        Yields:
            AgentNodeFrame (진행) / ErrorFrame (격리) / ResultFrame(payload.skill_ids)
        """
        if not skills:
            yield ErrorFrame(code="E_NO_SKILLS", message="확정할 스킬이 없음")
            return

        skill_ids: list[str] = []
        failed: list[dict] = []

        for skill in skills:
            node_type = skill.get("node_type", "?")
            # confirm = wizard 신뢰 경계 (사용자가 편집한 데이터). malformed 입력은 예외를 던지지 않고
            # 격리된 ErrorFrame으로 — staging 파싱 + 필수 키 + category(extract와 동일 검증)를 재확인.
            try:
                staging = NodeSpecStaging(**skill["staging"])
                name = skill["name"]
                description = skill["description"]
                # SKILL.md 본문(ADR-0017) — 편집된 입력이라 str 아니거나 빈 값이면 미저장(None) 격리.
                raw_instr = skill.get("instructions")
                instructions = raw_instr if isinstance(raw_instr, str) and raw_instr.strip() else None
                if staging.category not in _ALLOWED_CATEGORIES:
                    raise ValueError(
                        f"category '{staging.category}'가 DB CHECK 8영문에 없음: {sorted(_ALLOWED_CATEGORIES)}"
                    )
            except (KeyError, TypeError, ValueError, ValidationError) as e:
                failed.append({"node_type": node_type, "stage": "validate", "error": str(e)})
                yield ErrorFrame(code="E_SKILL_INVALID", message=f"확정 입력 검증 실패 ({node_type}): {e}")
                continue

            try:
                embedding = await self._embedder.embed(description)
            except Exception as e:
                failed.append({"node_type": node_type, "stage": "embed", "error": str(e)})
                yield ErrorFrame(code="E_EMBEDDING_FAILED", message=f"임베딩 실패 ({node_type}): {e}")
                continue

            yield AgentNodeFrame(agent_node_name=f"skills_builder.sop.create_draft.{node_type}")

            try:
                sid = await self._create_draft_skill.execute(
                    owner_user_id=user_id,
                    name=name,
                    description=description,
                    node_spec_staging=staging,
                    embedding=embedding,
                    instructions=instructions,  # ADR-0017 — SKILL.md 본문 → GCS 저장(use case 경유)
                )
            except Exception as e:
                failed.append({"node_type": node_type, "stage": "create_draft", "error": str(e)})
                yield ErrorFrame(code="E_CREATE_DRAFT_FAILED", message=f"DRAFT 생성 실패 ({node_type}): {e}")
                continue

            skill_ids.append(str(sid))

        yield ResultFrame(
            intent="build_skill",
            payload={
                "source_type": "sop",
                "skill_ids": skill_ids,
                "created_count": len(skill_ids),
                "failed_count": len(failed),
                "failed": failed,
                "user_id": str(user_id),
            },
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        document: DocumentBlock,
        personal_memory: list[MemoryEntry],
    ) -> str:
        """LLM 프롬프트 구성. **JSON 형식 강제** (XML 금지 — 메모리 룰).

        구조:
            - 시스템 지시 (역할/규칙)
            - personal_memory (JSON dump, 도메인 컨텍스트)
            - document blocks (JSON dump, text/heading/table 만 필터)
            - few-shot 예시 1건 (LLM 응답 품질 향상)
            - 출력 스키마 명시 (_ExtractedSkillNodeList JSON schema)
        """
        # 1) document blocks 필터링 + JSON 변환
        relevant_blocks = [
            b.model_dump(mode="json")
            for b in document.blocks
            if b.block_type in {"text", "heading", "table"}
        ]

        # 2) personal_memory JSON 변환
        memory_json = [m.model_dump(mode="json") for m in personal_memory]

        # 3) 시스템 지시
        instruction = (
            "당신은 사내 업무 자동화 SOP 문서를 분석해 워크플로우 노드(SkillNode)를 추출하는 어시스턴트입니다. "
            "SOP 문서의 단계별 작업 중 외부 시스템 호출/조건 분기/데이터 변환이 들어가는 단위를 "
            "SkillNode로 정의해주세요.\n\n"
            "출력 전체는 **반드시 JSON** 형식입니다 (XML 금지). "
            "단 instructions 필드의 *값*은 사람이 읽는 markdown 문자열입니다.\n"
            "각 SkillNode 필드:\n"
            "  - node_type: snake_case 식별자 (e.g. 'send_approval_email')\n"
            "  - name: 사람이 읽을 수 있는 한글 이름\n"
            "  - description: 노드 동작 설명 (한 문장)\n"
            f"  - category: 다음 중 하나 — {sorted(_ALLOWED_CATEGORIES)}\n"
            "  - risk_level: 'Low' / 'Medium' / 'High' / 'Restricted'\n"
            "  - inputs: JSON Schema (type=object + properties). **각 property는 반드시 `description`을 포함** — "
            "비전문가도 무슨 값을 넣어야 할지 알 수 있도록 한 줄 설명 + 구체적인 예시(예: ...)를 넣는다. "
            "특히 외부에서 발급되는 ID·토큰처럼 값을 추정하기 어려운 필드는 '어디서 얻는지'까지 적는다. "
            "선택지가 정해져 있으면 enum, 기본값이 있으면 default도 명시한다\n"
            "  - outputs: JSON Schema. 각 property에 무엇이 나오는지 `description`을 넣는다\n"
            "  - required_connections: list[str] (e.g. ['slack', 'google'])\n"
            "  - service_type: str | null (e.g. 'slack', 'google_workspace')\n"
            "  - instructions: 이 스킬의 SKILL.md 지침서 본문 (markdown 문자열). 사용자가 대화 중 읽고 "
            "선택할 수 있도록 '## When to use', '## Steps', '## Inputs/Outputs' 섹션을 포함한 설명 (ADR-0017)\n\n"
            "사용자의 personal_memory와 작업 패턴을 참고해 도메인 맥락 반영. "
            "추출 결과가 없으면 빈 배열 반환."
        )

        # 4) Few-shot 예시 (LLM 출력 품질 향상 — 형식·필드·카테고리 의도 명확화)
        few_shot_example = {
            "input_sop_snippet": (
                "고객 환불 요청이 접수되면 1) 매니저에게 슬랙 알림 2) 환불 금액이 5만원 초과면 "
                "승인 대기 3) 승인 후 결제 취소 API 호출"
            ),
            "expected_output": {
                "skill_nodes": [
                    {
                        "node_type": "refund_request_slack_alert",
                        "name": "환불 요청 매니저 알림",
                        "description": "환불 요청 접수 시 매니저 슬랙 채널에 알림",
                        "category": "action",
                        "risk_level": "Medium",
                        "inputs": {
                            "type": "object",
                            "properties": {
                                "refund_id": {"type": "string", "description": "환불 요청 건의 ID. 예: RF-10293"},
                                "amount": {"type": "number", "description": "환불 금액(원). 예: 35000"},
                                "channel": {"type": "string", "description": "Slack 채널. 예: '#cs-refund'"},
                            },
                            "required": ["refund_id", "amount"],
                        },
                        "outputs": {
                            "type": "object",
                            "properties": {"message_ts": {"type": "string", "description": "메시지 타임스탬프"}},
                        },
                        "required_connections": ["slack"],
                        "service_type": "slack",
                        "instructions": (
                            "## When to use\n환불 요청이 접수되어 담당 매니저에게 즉시 알려야 할 때.\n"
                            "## Steps\n1. 환불 요청 정보(refund_id, amount) 확인\n"
                            "2. 지정 Slack 채널에 알림 메시지 발송\n"
                            "## Inputs/Outputs\n- 입력: refund_id, amount, channel\n"
                            "- 출력: message_ts (메시지 타임스탬프)"
                        ),
                    },
                    {
                        "node_type": "refund_amount_threshold_check",
                        "name": "환불 금액 임계값 분기",
                        "description": "환불 금액이 임계값 초과 시 승인 대기, 이하면 자동 진행",
                        "category": "condition",
                        "risk_level": "High",
                        "inputs": {
                            "type": "object",
                            "properties": {
                                "amount": {"type": "number", "description": "판단 대상 환불 금액(원). 예: 35000"},
                                "threshold": {"type": "number", "default": 50000, "description": "분기 기준 금액(원)"},
                            },
                            "required": ["amount"],
                        },
                        "outputs": {
                            "type": "object",
                            "properties": {
                                "requires_approval": {"type": "boolean", "description": "승인 대기 필요 여부"},
                            },
                        },
                        "required_connections": [],
                        "service_type": None,
                        "instructions": (
                            "## When to use\n환불 금액에 따라 자동 승인 가능 여부를 분기해야 할 때.\n"
                            "## Steps\n1. 환불 금액과 임계값(기본 5만원) 비교\n"
                            "2. 초과 시 승인 대기, 이하면 자동 진행 플래그 설정\n"
                            "## Inputs/Outputs\n- 입력: amount, threshold\n- 출력: requires_approval (boolean)"
                        ),
                    },
                ],
            },
        }

        # 5) 출력 스키마 (LLM이 따라야 할 JSON 구조 — grammar-level 강제와 정합)
        output_schema = {
            "type": "object",
            "properties": {
                "skill_nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "node_type": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "category": {"type": "string", "enum": sorted(_ALLOWED_CATEGORIES)},
                            "risk_level": {"type": "string", "enum": ["Low", "Medium", "High", "Restricted"]},
                            "inputs": {"type": "object"},
                            "outputs": {"type": "object"},
                            "required_connections": {"type": "array", "items": {"type": "string"}},
                            "service_type": {"type": ["string", "null"]},
                            "instructions": {"type": "string"},
                        },
                        "required": [
                            "node_type", "name", "description", "category",
                            "risk_level", "inputs", "outputs", "required_connections", "instructions",
                        ],
                    },
                },
            },
            "required": ["skill_nodes"],
        }

        payload = {
            "instruction": instruction,
            "personal_memory": memory_json,
            "document": {
                "file_name": document.file_meta.file_name,
                "blocks": relevant_blocks,
            },
            "few_shot_example": few_shot_example,
            "output_schema": output_schema,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _convert_to_staging(ext: _ExtractedSkillNode) -> NodeSpecStaging:
        """LLM 추출 항목을 검증 → NodeSpecStaging 변환 (NodeDefinition은 publish 시 생성, Option B).

        검증:
        - category가 DB CHECK 8영문 내인지
        - risk_level이 RiskLevel enum 내인지 (`RiskLevel(...)` 변환 시 raise)
        """
        if ext.category not in _ALLOWED_CATEGORIES:
            raise ValueError(
                f"category '{ext.category}'가 DB CHECK 8영문에 없음. 가능: {sorted(_ALLOWED_CATEGORIES)}"
            )

        # SkillNode 검증 (Pydantic — risk_level이 RiskLevel enum이 아니면 raise, source 일관성)
        SkillNode(
            source_type="sop",
            source_id="",
            name=ext.name,
            description=ext.description,
            inputs=ext.inputs,
            outputs=ext.outputs,
            risk_level=RiskLevel(ext.risk_level),
        )

        return NodeSpecStaging(
            category=ext.category,
            input_schema=ext.inputs,
            output_schema=ext.outputs,
            risk_level=RiskLevel(ext.risk_level),
            required_connections=ext.required_connections,
            service_type=ext.service_type,
        )
