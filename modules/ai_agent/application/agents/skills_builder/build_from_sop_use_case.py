"""Skills Builder — SOP 문서(DocumentBlock) → LLM → wizard (ADR-0020 ③-a, 옵션 1 2단계 분리).

REQ-004 spec §2.2 BuildFromSOPUseCase. wizard 1차(Q8): 추출 결과를 사용자가 검토·수정 후 확정.

LLM 호출은 LLMPort stub으로 단위 테스트 가능, 실 endpoint(`llm-base` Modal) 배포 후 wiring.

흐름 (옵션 1 — 2단계 분리, LLM JSON 잘림 해소):
    [extract_metadata] DocumentBlock + personal_memory(list[MemoryEntry])
      → JSON prompt 구성 (XML 금지 — 메모리 룰)
      → LLM.generate_structured(prompt, _ExtractedSkillNodeMetaList)
      → ResultFrame(payload.skill_metas) — 메타 5필드만(node_type/name/description/category/risk_level)
      → 사용자 카드 그리드 표시, 1건 선택
    [extract_detail] DocumentBlock + 선택된 meta dict
      → JSON prompt 구성 (target_skill_meta 명시)
      → LLM.generate_structured(prompt, _ExtractedSkillNodeDetail)
      → ResultFrame(payload.skill_detail) — detail 5필드(inputs/outputs/instructions/...) + staging
      → 사용자 폼 prefill (frontend가 메타와 합쳐서)
    [confirm] 편집된 skills (메타 + detail 합친 형태)
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
   # 3단계: extract_metadata(user_id, document, personal_memory) → 카드 그리드 표시 →
   #        사용자 1건 선택 → extract_detail(user_id, document, meta=selected) → 폼 prefill →
   #        사용자 검토·수정 → confirm(user_id, skills)
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


class _ExtractedSkillNodeMeta(BaseModel):
    """1차 LLM 추출 — 메타 5필드만. 카드 그리드 표시용.

    옵션 1(2단계 분리)의 1차 응답 스키마. 사용자가 카드 선택 시 식별 정보로 detail 호출에 전달.
    """
    model_config = ConfigDict(frozen=True)

    node_type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: str                           # 영문 8종 (검증은 use case에서)
    risk_level: str                         # Low/Medium/High/Restricted


class _ExtractedSkillNodeMetaList(BaseModel):
    """1차 LLM structured output 컨테이너."""
    model_config = ConfigDict(frozen=True)

    skill_node_metas: list[_ExtractedSkillNodeMeta]


class _ExtractedSkillNodeDetail(BaseModel):
    """2차 LLM 추출 — 선택된 메타에 대한 detail 5필드. 폼 prefill용.

    옵션 1의 2차 응답 스키마. inputs/outputs JSON Schema + instructions markdown 등 토큰 무거운 필드.
    1차에서 받은 메타와 frontend가 합쳐서 사용자 폼에 prefill한다.

    `instructions`는 ADR-0017 이중 저장 중 SkillDocument(SKILL.md) 지침서 본문 —
    confirm 단계에서 GCS 저장된다(use case 경유).
    """
    model_config = ConfigDict(frozen=True)

    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    required_connections: list[str] = Field(default_factory=list)
    service_type: str | None = None
    instructions: str = Field(min_length=1)  # SkillDocument(SKILL.md) markdown body — ADR-0017


# ----------------------------------------------------------------------
# UseCase
# ----------------------------------------------------------------------


class BuildFromSOPUseCase:
    """SOP DocumentBlock → LLM 추출 → wizard 3단계 (ADR-0020 ③-a, Q8 wizard 1차 + 옵션 1 2단계 분리).

    - extract_metadata: 메타 5필드만 추출(node_type/name/description/category/risk_level), **저장 X** — 카드 그리드용
    - extract_detail: 선택된 메타에 대한 detail(inputs/outputs/instructions/...) + `NodeSpecStaging` 반환, **저장 X** — 폼 prefill용
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

    async def extract_metadata(
        self,
        user_id: UUID,
        document: DocumentBlock,
        personal_memory: list[MemoryEntry] | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        """wizard 1단계 — SOP에서 SkillNode 메타만 추출(카드 그리드용). **저장 안 함**.

        옵션 1(2단계 분리): 응답당 토큰을 줄여 LLM JSON 잘림(EOF) 해소. 메타 5필드만
        받고, 사용자가 카드 선택 시 frontend가 `extract_detail`을 호출해 detail을 채운다.

        Yields:
            AgentNodeFrame (진행) / ErrorFrame (실패) / ResultFrame(payload.skill_metas) — 메타 목록
        """
        personal_memory = personal_memory or []

        if not document.blocks:
            yield ErrorFrame(
                code="E_DOCUMENT_EMPTY",
                message=f"DocumentBlock(id={document.document_id})에 blocks 없음 — 추출할 내용 없음",
            )
            return

        yield AgentNodeFrame(agent_node_name="skills_builder.sop.parse_document")
        prompt = self._build_prompt_metadata(document, personal_memory)
        yield AgentNodeFrame(agent_node_name="skills_builder.sop.llm_extract_metadata")

        try:
            extracted = await self._llm.generate_structured(prompt, _ExtractedSkillNodeMetaList)
        except Exception as e:
            yield ErrorFrame(code="E_LLM_GENERATION_FAILED", message=f"LLM 호출 실패: {e}")
            return

        if not isinstance(extracted, _ExtractedSkillNodeMetaList):
            yield ErrorFrame(
                code="E_LLM_RESPONSE_INVALID",
                message=f"LLM 응답이 _ExtractedSkillNodeMetaList 형태 아님: {type(extracted).__name__}",
            )
            return

        if not extracted.skill_node_metas:
            yield ErrorFrame(
                code="E_NO_SKILLS_EXTRACTED",
                message="LLM이 SkillNode 메타를 추출하지 못함 (SOP 문서에 자동화 가능 작업 없음으로 판단)",
            )
            return

        # 각 메타 항목 검증 (category/risk_level은 DB CHECK 정합)
        skill_metas: list[dict] = []
        for meta in extracted.skill_node_metas:
            try:
                self._validate_meta(meta)
            except ValueError as e:
                yield ErrorFrame(
                    code="E_LLM_RESPONSE_INVALID",
                    message=f"LLM 추출 메타 검증 실패 ({meta.node_type}): {e}",
                )
                return
            skill_metas.append({
                "node_type": meta.node_type,
                "name": meta.name,
                "description": meta.description,
                "category": meta.category,
                "risk_level": meta.risk_level,
            })

        yield ResultFrame(
            intent="build_skill",
            payload={
                "source_type": "sop",
                "document_id": str(document.document_id),
                "file_name": document.file_meta.file_name,
                "skill_metas": skill_metas,  # 카드 그리드용 (사용자 선택 → extract_detail)
                "user_id": str(user_id),
            },
        )

    async def extract_detail(
        self,
        user_id: UUID,
        document: DocumentBlock,
        meta: dict,
        personal_memory: list[MemoryEntry] | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        """wizard 1.5단계 — 선택된 메타의 detail(inputs/outputs/instructions/...) 추출.

        옵션 1의 2차 호출. 1차에서 받은 메타와 합쳐 사용자 폼에 prefill된다.
        Stateless: frontend가 1차 메타 + source(document) 정보를 다시 전달.

        Args:
            meta: 1차에서 받은 메타 dict (node_type/name/description/category/risk_level).

        Yields:
            AgentNodeFrame (진행) / ErrorFrame (실패) / ResultFrame(payload.skill_detail) — 단건 detail
        """
        personal_memory = personal_memory or []

        if not document.blocks:
            yield ErrorFrame(
                code="E_DOCUMENT_EMPTY",
                message=f"DocumentBlock(id={document.document_id})에 blocks 없음 — 추출할 내용 없음",
            )
            return

        # 입력 meta dict 검증 — frontend가 1차 응답을 그대로 전달했는지
        try:
            meta_obj = _ExtractedSkillNodeMeta(**meta)
            self._validate_meta(meta_obj)
        except (TypeError, ValueError, ValidationError) as e:
            yield ErrorFrame(code="E_META_INVALID", message=f"입력 메타 검증 실패: {e}")
            return

        yield AgentNodeFrame(agent_node_name="skills_builder.sop.parse_document")
        prompt = self._build_prompt_detail(document, personal_memory, meta_obj)
        yield AgentNodeFrame(agent_node_name=f"skills_builder.sop.llm_extract_detail.{meta_obj.node_type}")

        try:
            detail = await self._llm.generate_structured(prompt, _ExtractedSkillNodeDetail)
        except Exception as e:
            yield ErrorFrame(code="E_LLM_GENERATION_FAILED", message=f"LLM 호출 실패: {e}")
            return

        if not isinstance(detail, _ExtractedSkillNodeDetail):
            yield ErrorFrame(
                code="E_LLM_RESPONSE_INVALID",
                message=f"LLM 응답이 _ExtractedSkillNodeDetail 형태 아님: {type(detail).__name__}",
            )
            return

        try:
            staging = self._convert_detail_to_staging(meta_obj, detail)
        except (KeyError, ValueError) as e:
            yield ErrorFrame(
                code="E_LLM_RESPONSE_INVALID",
                message=f"LLM detail 변환 실패 ({meta_obj.node_type}): {e}",
            )
            return

        yield ResultFrame(
            intent="build_skill",
            payload={
                "source_type": "sop",
                "document_id": str(document.document_id),
                "file_name": document.file_meta.file_name,
                "skill_detail": {
                    "node_type": meta_obj.node_type,            # 식별용 echo
                    "instructions": detail.instructions,
                    "inputs": detail.inputs,
                    "outputs": detail.outputs,
                    "required_connections": detail.required_connections,
                    "service_type": detail.service_type,
                    "staging": staging.model_dump(mode="json"),
                },
                "user_id": str(user_id),
            },
        )

    async def confirm(
        self,
        user_id: UUID,
        skills: list[dict],
    ) -> AsyncGenerator[SSEFrame, None]:
        """wizard 3단계 — 사용자가 편집·확정한 추출 결과 → personal DRAFT 스킬 생성.

        각 skill = `{node_type, name, description, instructions, staging:{...}}` (extract_metadata + extract_detail
        결과를 frontend가 합쳐 사용자가 편집한 형태). `CreateDraftSkillUseCase`로 DRAFT 생성 (Option B — NodeDefinition은 publish 시).

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
    def _build_prompt_metadata(
        document: DocumentBlock,
        personal_memory: list[MemoryEntry],
    ) -> str:
        """1차 LLM 프롬프트 — 메타 5필드만 추출(카드 그리드용). **JSON 형식 강제**.

        토큰을 가볍게 유지하기 위해 inputs/outputs JSON Schema + instructions markdown은
        2차(`_build_prompt_detail`)로 분리. 메타만으로도 사용자가 어느 노드를 선택할지 결정 가능.
        """
        relevant_blocks = [
            b.model_dump(mode="json")
            for b in document.blocks
            if b.block_type in {"text", "heading", "table"}
        ]
        memory_json = [m.model_dump(mode="json") for m in personal_memory]

        instruction = (
            "당신은 사내 업무 자동화 SOP 문서를 분석해 워크플로우 노드(SkillNode)를 추출하는 어시스턴트입니다. "
            "SOP 문서의 단계별 작업 중 외부 시스템 호출/조건 분기/데이터 변환이 들어가는 단위를 "
            "SkillNode로 정의해주세요.\n\n"
            "이 단계에서는 **메타 5필드만** 추출합니다 (입출력 스키마/지침서는 후속 단계에서 채움).\n"
            "각 SkillNode 메타 필드:\n"
            "  - node_type: snake_case 식별자 (e.g. 'send_approval_email')\n"
            "  - name: 사람이 읽을 수 있는 한글 이름\n"
            "  - description: 노드 동작 설명 (한 문장)\n"
            f"  - category: 다음 중 하나 — {sorted(_ALLOWED_CATEGORIES)}\n"
            "  - risk_level: 'Low' / 'Medium' / 'High' / 'Restricted'\n\n"
            "사용자의 personal_memory와 작업 패턴을 참고해 도메인 맥락 반영. "
            "추출 결과가 없으면 빈 배열 반환."
        )

        few_shot_example = {
            "input_sop_snippet": (
                "고객 환불 요청이 접수되면 1) 매니저에게 슬랙 알림 2) 환불 금액이 5만원 초과면 "
                "승인 대기 3) 승인 후 결제 취소 API 호출"
            ),
            "expected_output": {
                "skill_node_metas": [
                    {
                        "node_type": "refund_request_slack_alert",
                        "name": "환불 요청 매니저 알림",
                        "description": "환불 요청 접수 시 매니저 슬랙 채널에 알림",
                        "category": "action",
                        "risk_level": "Medium",
                    },
                    {
                        "node_type": "refund_amount_threshold_check",
                        "name": "환불 금액 임계값 분기",
                        "description": "환불 금액이 임계값 초과 시 승인 대기, 이하면 자동 진행",
                        "category": "condition",
                        "risk_level": "High",
                    },
                ],
            },
        }

        output_schema = {
            "type": "object",
            "properties": {
                "skill_node_metas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "node_type": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "category": {"type": "string", "enum": sorted(_ALLOWED_CATEGORIES)},
                            "risk_level": {"type": "string", "enum": ["Low", "Medium", "High", "Restricted"]},
                        },
                        "required": ["node_type", "name", "description", "category", "risk_level"],
                    },
                },
            },
            "required": ["skill_node_metas"],
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
    def _build_prompt_detail(
        document: DocumentBlock,
        personal_memory: list[MemoryEntry],
        meta: _ExtractedSkillNodeMeta,
    ) -> str:
        """2차 LLM 프롬프트 — 선택된 메타에 대한 detail 5필드 추출(폼 prefill용).

        SOP 전체 context를 함께 전달해 instructions(Steps 등)가 SOP 흐름 기반으로 생성되도록 한다.
        메타는 LLM에 echo하지 않음 — frontend가 1차 메타와 합쳐 사용.
        """
        relevant_blocks = [
            b.model_dump(mode="json")
            for b in document.blocks
            if b.block_type in {"text", "heading", "table"}
        ]
        memory_json = [m.model_dump(mode="json") for m in personal_memory]

        instruction = (
            "당신은 사내 업무 자동화 SOP 문서에서 추출된 SkillNode의 **상세 스펙(detail)을 채우는** 어시스턴트입니다. "
            "아래 `target_skill_meta`에 명시된 노드에 대해서만, SOP 문서를 근거로 다음 5필드를 생성하세요:\n\n"
            "  - inputs: JSON Schema (type=object + properties). **각 property는 반드시 `description`을 포함** — "
            "비전문가도 무슨 값을 넣어야 할지 알 수 있도록 한 줄 설명 + 구체적인 예시(예: ...)를 넣는다. "
            "특히 외부에서 발급되는 ID·토큰처럼 값을 추정하기 어려운 필드는 '어디서 얻는지'까지 적는다. "
            "선택지가 정해져 있으면 enum, 기본값이 있으면 default도 명시한다\n"
            "  - outputs: JSON Schema. 각 property에 무엇이 나오는지 `description`을 넣는다\n"
            "  - required_connections: list[str] (e.g. ['slack', 'google'])\n"
            "  - service_type: str | null (e.g. 'slack', 'google_workspace')\n"
            "  - instructions: 이 스킬의 SKILL.md 지침서 본문 (markdown 문자열). "
            "사용자가 대화 중 읽고 선택할 수 있도록 '## When to use', '## Steps', '## Inputs/Outputs' 섹션을 "
            "포함한 충분한 설명 (ADR-0017)\n\n"
            "출력 전체는 **반드시 JSON** 형식입니다 (XML 금지). "
            "단 instructions 필드의 *값*은 사람이 읽는 markdown 문자열입니다."
        )

        few_shot_example = {
            "input_meta": {
                "node_type": "refund_request_slack_alert",
                "name": "환불 요청 매니저 알림",
                "description": "환불 요청 접수 시 매니저 슬랙 채널에 알림",
                "category": "action",
                "risk_level": "Medium",
            },
            "expected_output": {
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
        }

        output_schema = {
            "type": "object",
            "properties": {
                "inputs": {"type": "object"},
                "outputs": {"type": "object"},
                "required_connections": {"type": "array", "items": {"type": "string"}},
                "service_type": {"type": ["string", "null"]},
                "instructions": {"type": "string"},
            },
            "required": ["inputs", "outputs", "required_connections", "instructions"],
        }

        payload = {
            "instruction": instruction,
            "personal_memory": memory_json,
            "document": {
                "file_name": document.file_meta.file_name,
                "blocks": relevant_blocks,
            },
            "target_skill_meta": meta.model_dump(mode="json"),
            "few_shot_example": few_shot_example,
            "output_schema": output_schema,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _validate_meta(meta: _ExtractedSkillNodeMeta) -> None:
        """메타 검증 — category가 DB CHECK 8영문 내, risk_level이 RiskLevel enum 내."""
        if meta.category not in _ALLOWED_CATEGORIES:
            raise ValueError(
                f"category '{meta.category}'가 DB CHECK 8영문에 없음. 가능: {sorted(_ALLOWED_CATEGORIES)}"
            )
        RiskLevel(meta.risk_level)  # raise ValueError if not in enum

    @staticmethod
    def _convert_detail_to_staging(
        meta: _ExtractedSkillNodeMeta,
        detail: _ExtractedSkillNodeDetail,
    ) -> NodeSpecStaging:
        """메타 + detail → NodeSpecStaging (NodeDefinition은 publish 시 생성, Option B).

        category/risk_level은 메타에서, input/output/connections/service_type은 detail에서 가져온다.
        SkillNode Pydantic 검증으로 source 일관성도 확인.
        """
        SkillNode(
            source_type="sop",
            source_id="",
            name=meta.name,
            description=meta.description,
            inputs=detail.inputs,
            outputs=detail.outputs,
            risk_level=RiskLevel(meta.risk_level),
        )

        return NodeSpecStaging(
            category=meta.category,
            input_schema=detail.inputs,
            output_schema=detail.outputs,
            risk_level=RiskLevel(meta.risk_level),
            required_connections=detail.required_connections,
            service_type=detail.service_type,
        )
