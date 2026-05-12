"""Skills Builder — SOP 문서(DocumentBlock) → LLM → SkillNode → NodeDefinition upsert.

REQ-004 spec §2.2 BuildFromSOPUseCase.

LLM 의존 작업이라 5/16 plan에 본격 구현 예정. 본 모듈은 **skeleton** —
LLM 호출 부분은 LLMPort stub으로 단위 테스트 가능, 실 endpoint(`llm-base` Modal)
배포 후 wiring만 하면 production-ready.

흐름:
    DocumentBlock (doc_parser 산출물)
      + personal_memory (Orchestrator가 미리 로드한 list[MemoryEntry])
      → JSON prompt 구성 (XML 금지 — 메모리 룰)
      → LLM.generate_structured(prompt, ExtractedSkillNodeList) 호출
      → 응답 검증 + SkillNode 변환
      → NodeDefinition 변환 (embedding 포함)
      → NodeDefinitionRepository.upsert()
      → SSE 프레임 yield

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

3) Composition root (api_server 또는 운영 스크립트):
   ```python
   from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
   from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
   from storage.repositories import PgNodeDefinitionRepository  # 황대원 5/15

   use_case = BuildFromSOPUseCase(
       node_def_repo=PgNodeDefinitionRepository(...),
       embedder=ModalEmbeddingAdapter(base_url=os.environ["EMBEDDING_BASE_URL"]),
       llm=ModalLLMAdapter(),  # MODAL_TOKEN_ID/SECRET 환경변수 자동 사용
   )
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
from uuid import UUID, uuid5

from common_schemas import DocumentBlock, MemoryEntry
from common_schemas.enums import RiskLevel
from common_schemas.transport import AgentNodeFrame, ErrorFrame, ResultFrame, SSEFrame
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository
from pydantic import BaseModel, ConfigDict, Field

from ....domain.entities.skill_node import SkillNode
from ....domain.ports.llm_port import LLMPort


# uuid5 namespace for skills builder generated nodes (SOP source).
# node_id = uuid5(_NS, f"sop:{document_id}:{node_type}") — 같은 SOP에서 추출된
# 같은 node_type은 항상 같은 node_id 생성 → idempotent upsert.
# industry_default와 다른 source라 prefix "sop:"로 namespace 분리.
_SKILLS_BUILDER_NS = uuid5(UUID("00000000-0000-0000-0000-000000000000"), "workflow-automation.skills_builder")

# DB CHECK 영문 8종 (`009_node_definitions.sql`).
_ALLOWED_CATEGORIES = {"trigger", "action", "condition", "transform", "ai", "integration", "utility", "output"}


# ----------------------------------------------------------------------
# LLM structured response 래퍼
# ----------------------------------------------------------------------


class _ExtractedSkillNode(BaseModel):
    """LLM이 SOP에서 추출한 SkillNode 1건 (BuildFromSOP 내부 표현).

    LLM 응답 검증용 — Pydantic이 자동 validate.
    NodeDefinition 변환 시 추가 메타(node_id/version/parameter_schema/embedding)는 use case가 채움.
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


class _ExtractedSkillNodeList(BaseModel):
    """LLM structured output 컨테이너."""
    model_config = ConfigDict(frozen=True)

    skill_nodes: list[_ExtractedSkillNode]


# ----------------------------------------------------------------------
# UseCase
# ----------------------------------------------------------------------


class BuildFromSOPUseCase:
    """SOP DocumentBlock → LLM → SkillNode 추출 → NodeDefinition upsert.

    Sprint 3 v1 skeleton:
    - LLMPort.generate_structured 호출로 SkillNode 목록 추출
    - JSON 형식 강제 (메모리 룰: LLM 입력/출력 무조건 JSON, XML 금지)
    - 부분 실패 격리 (embed/upsert 단계만, convert는 fail-fast)
    """

    def __init__(
        self,
        node_def_repo: NodeDefinitionRepository,
        embedder: EmbedderPort,
        llm: LLMPort,
    ) -> None:
        self._repo = node_def_repo
        self._embedder = embedder
        self._llm = llm

    async def execute(
        self,
        user_id: UUID,
        document: DocumentBlock,
        personal_memory: list[MemoryEntry] | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        """SOP DocumentBlock에서 SkillNode 추출 → nodes_graph 카탈로그 upsert.

        Args:
            user_id: 호출 사용자
            document: doc_parser 산출물 (text/heading/table 등 ContentBlock 포함)
            personal_memory: Orchestrator가 미리 로드한 사용자 메모리 (LLM 프롬프트 컨텍스트)

        Yields:
            AgentNodeFrame (진행) / ErrorFrame (개별 실패) / ResultFrame (최종)
        """
        personal_memory = personal_memory or []

        # 1. DocumentBlock 검증
        if not document.blocks:
            yield ErrorFrame(
                code="E_DOCUMENT_EMPTY",
                message=f"DocumentBlock(id={document.document_id})에 blocks 없음 — 추출할 내용 없음",
            )
            return

        yield AgentNodeFrame(agent_node_name="skills_builder.sop.parse_document")

        # 2. LLM 프롬프트 구성 (JSON 형식 강제)
        prompt = self._build_prompt(document, personal_memory)

        yield AgentNodeFrame(agent_node_name="skills_builder.sop.llm_extract")

        # 3. LLM 호출 (generate_structured)
        try:
            extracted = await self._llm.generate_structured(prompt, _ExtractedSkillNodeList)
        except Exception as e:
            yield ErrorFrame(
                code="E_LLM_GENERATION_FAILED",
                message=f"LLM 호출 실패: {e}",
            )
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

        # 4. 각 추출 항목 처리 (부분 실패 격리 정책)
        #
        # - convert/validate 실패 (LLM 응답이 비유효): 전체 중단.
        #   LLM 응답이 broken이면 일관성 위해 전체 재실행 권장.
        # - embed/upsert 실패 (외부 의존성 runtime 오류): 해당 노드만 격리,
        #   다른 노드 계속. ResultFrame.failed_node_types에 기록.
        # - uuid5 deterministic(같은 SOP·node_type) → 부분 실패 후 재실행 안전.
        upserted_node_types: list[str] = []
        failed_node_types: list[dict] = []

        for ext in extracted.skill_nodes:
            try:
                node_def = self._convert_to_node_definition(ext, document.document_id)
            except (KeyError, ValueError) as e:
                yield ErrorFrame(
                    code="E_LLM_RESPONSE_INVALID",
                    message=f"LLM 추출 항목 변환 실패 ({ext.node_type}): {e}",
                )
                return

            # 임베딩 (외부 의존성 — 격리)
            try:
                node_def.embedding = await self._embedder.embed(node_def.description)
            except Exception as e:
                failed_node_types.append({
                    "node_type": node_def.node_type,
                    "stage": "embed",
                    "error": str(e),
                })
                yield ErrorFrame(
                    code="E_EMBEDDING_FAILED",
                    message=f"임베딩 실패 ({node_def.node_type}): {e}",
                )
                continue

            yield AgentNodeFrame(agent_node_name=f"skills_builder.sop.upsert.{node_def.node_type}")

            # upsert (외부 의존성 — 격리)
            try:
                await self._repo.upsert(node_def)
            except Exception as e:
                failed_node_types.append({
                    "node_type": node_def.node_type,
                    "stage": "upsert",
                    "error": str(e),
                })
                yield ErrorFrame(
                    code="E_UPSERT_FAILED",
                    message=f"upsert 실패 ({node_def.node_type}): {e}",
                )
                continue

            upserted_node_types.append(node_def.node_type)

        # 5. 결과 프레임
        yield ResultFrame(
            intent="build_skill",
            payload={
                "source_type": "sop",
                "document_id": str(document.document_id),
                "file_name": document.file_meta.file_name,
                "upserted_count": len(upserted_node_types),
                "failed_count": len(failed_node_types),
                "node_types": upserted_node_types,
                "failed_node_types": failed_node_types,
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
            "출력은 **반드시 JSON** 형식이며, XML/Markdown 사용 금지입니다. "
            "각 SkillNode 필드:\n"
            "  - node_type: snake_case 식별자 (e.g. 'send_approval_email')\n"
            "  - name: 사람이 읽을 수 있는 한글 이름\n"
            "  - description: 노드 동작 설명 (한 문장)\n"
            f"  - category: 다음 중 하나 — {sorted(_ALLOWED_CATEGORIES)}\n"
            "  - risk_level: 'Low' / 'Medium' / 'High' / 'Restricted'\n"
            "  - inputs: JSON Schema (type=object + properties)\n"
            "  - outputs: JSON Schema\n"
            "  - required_connections: list[str] (e.g. ['slack', 'google'])\n"
            "  - service_type: str | null (e.g. 'slack', 'google_workspace')\n\n"
            "사용자의 personal_memory와 작업 패턴을 참고해 도메인 맥락 반영. "
            "추출 결과가 없으면 빈 배열 반환."
        )

        # 4) Few-shot 예시 (LLM 출력 품질 향상 — 형식·필드·카테고리 의도 명확화)
        few_shot_example = {
            "input_sop_snippet": "고객 환불 요청이 접수되면 1) 매니저에게 슬랙 알림 2) 환불 금액이 5만원 초과면 승인 대기 3) 승인 후 결제 취소 API 호출",
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
                                "refund_id": {"type": "string"},
                                "amount": {"type": "number"},
                                "channel": {"type": "string"},
                            },
                            "required": ["refund_id", "amount"],
                        },
                        "outputs": {
                            "type": "object",
                            "properties": {"message_ts": {"type": "string"}},
                        },
                        "required_connections": ["slack"],
                        "service_type": "slack",
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
                                "amount": {"type": "number"},
                                "threshold": {"type": "number", "default": 50000},
                            },
                            "required": ["amount"],
                        },
                        "outputs": {
                            "type": "object",
                            "properties": {
                                "requires_approval": {"type": "boolean"},
                            },
                        },
                        "required_connections": [],
                        "service_type": None,
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
                        },
                        "required": [
                            "node_type", "name", "description", "category",
                            "risk_level", "inputs", "outputs", "required_connections",
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
    def _convert_to_node_definition(
        ext: _ExtractedSkillNode,
        document_id: UUID,
    ) -> NodeDefinition:
        """LLM 추출 항목을 SkillNode 검증 → NodeDefinition 변환.

        검증:
        - category가 DB CHECK 8영문 내인지
        - risk_level이 RiskLevel enum 내인지 (Pydantic이 자동 raise)
        """
        if ext.category not in _ALLOWED_CATEGORIES:
            raise ValueError(
                f"category '{ext.category}'가 DB CHECK 8영문에 없음. 가능: {sorted(_ALLOWED_CATEGORIES)}"
            )

        # SkillNode 검증 (Pydantic — risk_level이 RiskLevel enum이 아니면 raise)
        SkillNode(
            source_type="sop",
            source_id=str(document_id),
            name=ext.name,
            description=ext.description,
            inputs=ext.inputs,
            outputs=ext.outputs,
            risk_level=RiskLevel(ext.risk_level),
        )

        return NodeDefinition(
            node_id=uuid5(_SKILLS_BUILDER_NS, f"sop:{document_id}:{ext.node_type}"),
            node_type=ext.node_type,
            name=ext.name,
            category=ext.category,
            version="1.0.0",
            input_schema=ext.inputs,
            output_schema=ext.outputs,
            parameter_schema={},
            risk_level=RiskLevel(ext.risk_level),
            required_connections=ext.required_connections,
            description=ext.description,
            is_mvp=False,  # SOP 추출 = 사용자 도메인 노드, MVP 카탈로그 아님
            service_type=ext.service_type,
            embedding=None,  # 호출자가 embedder로 채움
        )
