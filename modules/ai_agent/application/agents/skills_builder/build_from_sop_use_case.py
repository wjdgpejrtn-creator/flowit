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
      → LLM.generate_structured(prompt, _ExtractedSkillNodeDetail)  ← inputs/outputs/instructions(SKILL.md) "LLM 보강"
      → T4: SOP 텍스트를 SkeletonEntityExtractor "발화"로 결정적 스켈레톤 조립(ADR-0028 D2/D3)
      → T5: AssembledDraft → COMPOSER.md(결정적) + 정밀 BINDS(bound_node_types) 매핑(D4)
            (스켈레톤 미매칭 시 LLM composer_instructions 폴백)
      → ResultFrame(payload.skill_detail) — detail + staging + skeleton_name + bound_node_types
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
import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from common_schemas import Chunk, ContentBlock, DocumentBlock, MemoryEntry
from common_schemas.enums import RiskLevel
from common_schemas.transport import AgentNodeFrame, ErrorFrame, ResultFrame, SSEFrame
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from skills_marketplace.application.use_cases import CreateDraftSkillUseCase
from skills_marketplace.domain.value_objects import NodeSpecStaging

from ....domain.entities.skill_node import SkillNode
from ....domain.ports.llm_port import LLMPort
from ....domain.services.skeleton_assembler import SkeletonAssembler
from ....domain.services.skeleton_composer_mapper import SkeletonComposerMapper

_logger = logging.getLogger(__name__)

# DB CHECK 영문 8종 (`009_node_definitions.sql`).
_ALLOWED_CATEGORIES = {"trigger", "action", "condition", "transform", "ai", "integration", "utility", "output"}

# llm-base llama-server `--ctx-size`(8192)에는 입력 프롬프트 + 출력이 **함께** 들어가야 한다.
# 전체 문서를 한 번에 넣으면 입력만 8192를 초과해 400(exceed_context_size)으로 죽는다 — 그래서
# 청크 기반 map-reduce(메타)/RAG(detail)로 입력을 토큰 예산 안에 자른다.
#
# 토큰 추정: 청커가 char_estimate(char×0.7) 모드라 영속된 청크의 token_count는 신뢰 불가 +
# 미저장(컬럼 없음)이다. cl100k 한국어는 char당 토큰이 크므로(최대 ~2.5) **char×2.5를
# 상한 추정치**로 써서 "실제 토큰 ≤ 추정치 ≤ 예산"을 보장한다(과소추정→초과를 원천 차단).
_CTX_SIZE = 8192
# 한 LLM 호출에 넣을 문서 블록의 입력 토큰 예산(배치 경계). instruction/few-shot/output 여유 확보.
_METADATA_INPUT_TOKEN_BUDGET = 2500
_DETAIL_INPUT_TOKEN_BUDGET = 1800
# 출력 예산 — 메타 5필드×N은 작고, detail은 instructions/composer_instructions markdown이라 크다.
_METADATA_OUTPUT_MAX_TOKENS = 1800
_DETAIL_OUTPUT_MAX_TOKENS = 3500
# 폭주(거대 문서) 방지 — 초과 배치는 절단하고 log로 노출한다(무음 캡 금지).
_MAX_EXTRACT_BATCHES = 24
_REL_BLOCK_TYPES = {"text", "heading", "table"}


def _estimate_tokens(text: str) -> int:
    """cl100k 한국어 상한 추정(char×2.5). 실제 토큰 ≤ 추정치라 배치 예산으로 안전(과소추정 방지)."""
    return int(len(text) * 2.5) + 1


def _batch_blocks_by_budget(
    blocks: list[ContentBlock], budget: int
) -> list[list[ContentBlock]]:
    """블록을 입력 토큰 예산 이하 배치들로 분할. 단일 블록이 예산을 넘어도 그 블록만 단독 배치."""
    batches: list[list[ContentBlock]] = []
    current: list[ContentBlock] = []
    current_tokens = 0
    for block in blocks:
        t = _estimate_tokens(block.content or "")
        if current and current_tokens + t > budget:
            batches.append(current)
            current, current_tokens = [], 0
        current.append(block)
        current_tokens += t
    if current:
        batches.append(current)
    return batches


def _cosine(a: list[float], b: list[float]) -> float:
    """순수 코사인 유사도 (numpy 미사용 — skills-builder 런타임 의존 최소화)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _select_blocks_for_meta(
    chunks: list[Chunk], query_embedding: list[float], budget: int
) -> list[ContentBlock]:
    """detail용 — 선택 메타와 임베딩 유사도 상위 청크 블록을 예산 이하로 고른다(RAG).

    임베딩 있는 청크는 cosine 내림차순, 없는 청크는 뒤로. 동률·임베딩 부재 시 chunk_index 순.
    문서 흐름(instructions의 Steps 순서)을 위해 최종 선택은 chunk_index 오름차순으로 복원한다.
    """
    rel = [c for c in chunks if c.block.block_type in _REL_BLOCK_TYPES]
    scored = [
        (
            _cosine(query_embedding, c.embedding) if c.embedding else -1.0,
            c.chunk_index,
            c,
        )
        for c in rel
    ]
    scored.sort(key=lambda t: (-t[0], t[1]))
    picked: list[Chunk] = []
    used = 0
    for _score, _idx, c in scored:
        t = _estimate_tokens(c.block.content or "")
        if picked and used + t > budget:
            break
        picked.append(c)
        used += t
    picked.sort(key=lambda c: c.chunk_index)  # 문서 흐름 복원
    return [c.block for c in picked]


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
    """2차 LLM 추출 — 선택된 메타에 대한 detail 필드. 폼 prefill용.

    옵션 1의 2차 응답 스키마. inputs/outputs JSON Schema + instructions/composer_instructions markdown 등
    토큰 무거운 필드.
    1차에서 받은 메타와 frontend가 합쳐서 사용자 폼에 prefill한다.

    `instructions`는 ADR-0017 이중 저장 중 SkillDocument(SKILL.md) 지침서 본문 —
    confirm 단계에서 GCS 저장된다(use case 경유).
    `composer_instructions`는 ADR-0024 2-md 중 COMPOSER.md 본문 — 워크플로우 생성 시 drafter가
    노드 구성에 주입하는 "이 스킬을 쓰려면 어떤 노드를 엮어야 하는가" 지침(#372 결함 A 해소). optional.
    """
    model_config = ConfigDict(frozen=True)

    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    required_connections: list[str] = Field(default_factory=list)
    service_type: str | None = None
    instructions: str = Field(min_length=1)  # SkillDocument(SKILL.md) markdown body — ADR-0017
    composer_instructions: str = ""          # SkillDocument(COMPOSER.md) body — ADR-0024 (optional)


# ----------------------------------------------------------------------
# UseCase
# ----------------------------------------------------------------------


class BuildFromSOPUseCase:
    """SOP DocumentBlock → LLM 추출 → wizard 3단계 (ADR-0020 ③-a, Q8 wizard 1차 + 옵션 1 2단계 분리).

    - extract_metadata: 메타 5필드(node_type/name/description/category/risk_level) 추출, **저장 X** — 카드 그리드용
    - extract_detail: 선택된 메타의 detail(inputs/outputs/instructions/composer_instructions/...) +
      `NodeSpecStaging` 반환, **저장 X** — 폼 prefill용
    - confirm: 편집 결과 → CreateDraftSkillUseCase로 personal DRAFT 생성 (Option B — NodeDefinition은 publish 시점)
    - JSON 강제 (LLM 입출력), category/risk_level 검증
    """

    def __init__(
        self,
        create_draft_skill: CreateDraftSkillUseCase,
        embedder: EmbedderPort,
        llm: LLMPort,
        assembler: SkeletonAssembler | None = None,
        composer_mapper: SkeletonComposerMapper | None = None,
    ) -> None:
        self._create_draft_skill = create_draft_skill
        self._embedder = embedder
        self._llm = llm
        # T4/T5(ADR-0028): SOP 텍스트를 결정적 스켈레톤으로 조립(assembler)하고 그 구조를
        # COMPOSER.md + 정밀 BINDS로 매핑(composer_mapper)한다. 둘 다 순수 도메인 서비스라
        # 기본 생성(의존성 무, composition root 주입 불요 — 기존 3-인자 와이어링 호환).
        self._assembler = assembler or SkeletonAssembler()
        self._composer_mapper = composer_mapper or SkeletonComposerMapper()

    async def extract_metadata(
        self,
        user_id: UUID,
        document: DocumentBlock,
        personal_memory: list[MemoryEntry] | None = None,
        chunks: list[Chunk] | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        """wizard 1단계 — SOP에서 SkillNode 메타만 추출(카드 그리드용). **저장 안 함**.

        옵션 1(2단계 분리): 응답당 토큰을 줄여 LLM JSON 잘림(EOF) 해소. 메타 5필드만
        받고, 사용자가 카드 선택 시 frontend가 `extract_detail`을 호출해 detail을 채운다.

        **청크 map-reduce(옵션 C)**: `chunks`가 주어지면 청크 블록을 입력 토큰 예산 배치로 나눠
        배치별 LLM 추출 후 메타를 node_type로 병합·dedup한다 — 전체 문서를 한 프롬프트에 넣어
        8192 컨텍스트를 초과(exceed_context_size 400)하던 문제 해소. 청크가 없으면(구 문서/
        합성 템플릿) 전체 문서 단일 호출로 폴백(회귀 0).

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

        # 입력 블록 소스: 청크 있으면 청크 블록(map-reduce), 없으면 전체 문서 블록(폴백).
        if chunks:
            source_blocks = [c.block for c in chunks if c.block.block_type in _REL_BLOCK_TYPES]
        else:
            source_blocks = [b for b in document.blocks if b.block_type in _REL_BLOCK_TYPES]
        batches = _batch_blocks_by_budget(source_blocks, _METADATA_INPUT_TOKEN_BUDGET)
        if len(batches) > _MAX_EXTRACT_BATCHES:
            _logger.warning(
                "SOP 메타 추출: 배치 %d개 → 상한 %d개로 절단(거대 문서, 후미 누락 가능)",
                len(batches), _MAX_EXTRACT_BATCHES,
            )
            batches = batches[:_MAX_EXTRACT_BATCHES]

        # map: 배치별 메타 추출 → reduce: node_type 기준 병합·dedup(앞 배치 우선).
        # 배치 1건 실패는 비치명적(부분 추출 > 전체 실패)이나, **전 배치가 실패**하면 원인을
        # 보존해 정확한 에러 코드로 노출한다(예외→GENERATION_FAILED / 형태불일치→RESPONSE_INVALID).
        merged: dict[str, dict] = {}
        ok_count = 0
        last_error: tuple[str, str] | None = None  # (code, message)
        for i, batch in enumerate(batches):
            prompt = self._build_prompt_metadata(document.file_meta.file_name, batch, personal_memory)
            yield AgentNodeFrame(
                agent_node_name=f"skills_builder.sop.llm_extract_metadata.batch{i + 1}of{len(batches)}"
            )
            try:
                extracted = await self._llm.generate_structured(
                    prompt, _ExtractedSkillNodeMetaList, max_tokens=_METADATA_OUTPUT_MAX_TOKENS
                )
            except Exception as e:
                _logger.warning("SOP 메타 추출 배치 %d 실패(건너뜀): %s", i + 1, e)
                last_error = ("E_LLM_GENERATION_FAILED", f"LLM 호출 실패: {e}")
                continue
            if not isinstance(extracted, _ExtractedSkillNodeMetaList):
                _logger.warning("SOP 메타 추출 배치 %d 응답 형태 불일치(건너뜀)", i + 1)
                last_error = (
                    "E_LLM_RESPONSE_INVALID",
                    f"LLM 응답이 _ExtractedSkillNodeMetaList 형태 아님: {type(extracted).__name__}",
                )
                continue
            ok_count += 1
            for meta in extracted.skill_node_metas:
                try:
                    self._validate_meta(meta)
                except ValueError as e:
                    _logger.warning("SOP 메타 검증 실패(건너뜀) %s: %s", meta.node_type, e)
                    continue
                merged.setdefault(meta.node_type, {
                    "node_type": meta.node_type,
                    "name": meta.name,
                    "description": meta.description,
                    "category": meta.category,
                    "risk_level": meta.risk_level,
                })

        skill_metas = list(merged.values())
        if not skill_metas:
            # 유효 응답이 하나도 없었으면(전 배치 예외/형태불일치) 원인 코드를 그대로 surface.
            if ok_count == 0 and last_error is not None:
                yield ErrorFrame(code=last_error[0], message=last_error[1])
                return
            yield ErrorFrame(
                code="E_NO_SKILLS_EXTRACTED",
                message="LLM이 SkillNode 메타를 추출하지 못함 (SOP 문서에 자동화 가능 작업 없음으로 판단)",
            )
            return

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
        chunks: list[Chunk] | None = None,
    ) -> AsyncGenerator[SSEFrame, None]:
        """wizard 1.5단계 — 선택된 메타의 detail(inputs/outputs/instructions/...) 추출.

        옵션 1의 2차 호출. 1차에서 받은 메타와 합쳐 사용자 폼에 prefill된다.
        Stateless: frontend가 1차 메타 + source(document) 정보를 다시 전달.

        **청크 RAG(옵션 C)**: `chunks`(임베딩 포함)가 주어지면 선택 메타(name+description)를 임베딩해
        유사도 상위 청크만 입력 토큰 예산 안에 골라 넣는다 — detail은 출력(markdown)이 커서 입력을
        타이트하게 잡아야 8192 안에 입력+출력이 함께 들어간다. 청크가 없으면 전체 문서 블록으로 폴백.

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

        # 입력 블록 선택: 청크 있으면 메타 임베딩 RAG로 관련 청크만, 없으면 전체 문서(폴백).
        if chunks:
            try:
                query_embedding = await self._embedder.embed(f"{meta_obj.name} {meta_obj.description}")
                detail_blocks = _select_blocks_for_meta(
                    chunks, query_embedding, _DETAIL_INPUT_TOKEN_BUDGET
                )
            except Exception as e:
                # 임베딩 실패는 비치명적 — chunk_index 순 예산 절단으로 폴백.
                _logger.warning("detail RAG 임베딩 실패(예산 절단 폴백): %s", e)
                detail_blocks = _batch_blocks_by_budget(
                    [c.block for c in chunks if c.block.block_type in _REL_BLOCK_TYPES],
                    _DETAIL_INPUT_TOKEN_BUDGET,
                )[0] if chunks else []
        else:
            relevant = [b for b in document.blocks if b.block_type in _REL_BLOCK_TYPES]
            detail_blocks = _batch_blocks_by_budget(relevant, _DETAIL_INPUT_TOKEN_BUDGET)[0] if relevant else []

        prompt = self._build_prompt_detail(
            document.file_meta.file_name, detail_blocks, personal_memory, meta_obj
        )
        yield AgentNodeFrame(agent_node_name=f"skills_builder.sop.llm_extract_detail.{meta_obj.node_type}")

        try:
            detail = await self._llm.generate_structured(
                prompt, _ExtractedSkillNodeDetail, max_tokens=_DETAIL_OUTPUT_MAX_TOKENS
            )
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

        # T4(ADR-0028) — SOP 텍스트를 SkeletonEntityExtractor "발화" 자리에 넣어 결정적 스켈레톤
        # 조립. 추출기는 순수 키워드 매칭이라 발화 대신 SOP 본문+스킬 메타를 먹여도 동작(D2).
        yield AgentNodeFrame(agent_node_name="skills_builder.sop.search_skeleton")
        utterance = self._build_skill_utterance(meta_obj, document)
        draft = self._assembler.assemble(utterance)

        if draft is not None:
            # T5(ADR-0028 D2/D4) — 결정적 조립 구조 → COMPOSER.md(결정적) + 정밀 BINDS.
            # 구조는 코드가 결정(§6.6), LLM의 자유 composer_instructions를 대체한다.
            yield AgentNodeFrame(
                agent_node_name=f"skills_builder.sop.assemble_skill.{draft.skeleton_name}"
            )
            mapping = self._composer_mapper.map(draft)
            composer_instructions = mapping.composer_instructions
            bound_node_types = list(mapping.bound_node_types)
            skeleton_name: str | None = mapping.skeleton_name
        else:
            # 확신 가는 스켈레톤 매칭 없음(중첩 합성·불완전 커버리지 등) → 구조 결정 불가 →
            # LLM 자유추출 composer_instructions로 폴백(정밀 BINDS 없음, coarse BINDS 유지).
            composer_instructions = detail.composer_instructions
            bound_node_types = []
            skeleton_name = None

        yield ResultFrame(
            intent="build_skill",
            payload={
                "source_type": "sop",
                "document_id": str(document.document_id),
                "file_name": document.file_meta.file_name,
                "skill_detail": {
                    "node_type": meta_obj.node_type,            # 식별용 echo
                    "instructions": detail.instructions,
                    "composer_instructions": composer_instructions,  # COMPOSER.md (결정적 또는 LLM 폴백)
                    "inputs": detail.inputs,
                    "outputs": detail.outputs,
                    "required_connections": detail.required_connections,
                    "service_type": detail.service_type,
                    "staging": staging.model_dump(mode="json"),
                    # ADR-0028 D4 — 스켈레톤 유래 정밀 BINDS 원천(스캐폴드 실노드). 영속화/projector
                    # 정밀화는 O3(조장 합의) 후속 — 현재는 산출물 노출만(콜러블 use case 우선).
                    "skeleton_name": skeleton_name,
                    "bound_node_types": bound_node_types,
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

        각 skill = `{node_type, name, description, instructions, composer_instructions, staging:{...}}`
        (extract_metadata + extract_detail 결과를 frontend가 합쳐 편집한 형태). `CreateDraftSkillUseCase`로 DRAFT 생성
        (Option B — NodeDefinition은 publish 시).

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
                # COMPOSER.md 본문(ADR-0024) — 동일 신뢰 경계. 누락/빈 값이면 None(노드 지침만 있는 스킬).
                raw_composer = skill.get("composer_instructions")
                composer_instructions = (
                    raw_composer if isinstance(raw_composer, str) and raw_composer.strip() else None
                )
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
                    composer_instructions=composer_instructions,  # ADR-0024 — COMPOSER.md 본문 → GCS 2-md
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
    def _build_skill_utterance(
        meta: _ExtractedSkillNodeMeta,
        document: DocumentBlock,
    ) -> str:
        """SOP 텍스트를 SkeletonEntityExtractor "발화" 자리에 넣을 텍스트로 합성 (ADR-0028 T4).

        스킬이 무엇인지(name·description) + SOP 본문(도메인 노드 어휘)을 합쳐 렉시컬 추출기에
        먹인다 — 추출기는 순수 키워드 매칭이라 발화 대신 SOP를 먹여도 그대로 동작(D2). 메타를
        앞에 두어 "이 스킬"의 동작 어휘(예: "슬랙으로 알림")가 sink/source 슬롯에 먼저 진입하게 한다.
        """
        parts = [meta.name, meta.description]
        parts.extend(
            b.content
            for b in document.blocks
            if b.block_type in {"text", "heading", "table"} and b.content
        )
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _build_prompt_metadata(
        file_name: str,
        blocks: list[ContentBlock],
        personal_memory: list[MemoryEntry],
    ) -> str:
        """1차 LLM 프롬프트 — 메타 5필드만 추출(카드 그리드용). **JSON 형식 강제**.

        토큰을 가볍게 유지하기 위해 inputs/outputs JSON Schema + instructions markdown은
        2차(`_build_prompt_detail`)로 분리. 메타만으로도 사용자가 어느 노드를 선택할지 결정 가능.
        `blocks`는 호출자가 이미 관련 타입 필터 + 토큰 예산 배치를 적용한 부분집합이다(map-reduce).
        """
        relevant_blocks = [b.model_dump(mode="json") for b in blocks]
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
                "file_name": file_name,
                "blocks": relevant_blocks,
            },
            "few_shot_example": few_shot_example,
            "output_schema": output_schema,
        }

        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _build_prompt_detail(
        file_name: str,
        blocks: list[ContentBlock],
        personal_memory: list[MemoryEntry],
        meta: _ExtractedSkillNodeMeta,
    ) -> str:
        """2차 LLM 프롬프트 — 선택된 메타에 대한 detail 5필드 추출(폼 prefill용).

        SOP context를 함께 전달해 instructions(Steps 등)가 SOP 흐름 기반으로 생성되도록 한다.
        `blocks`는 호출자가 선택 메타와 관련도 높은 청크로 RAG 선별 + 토큰 예산 적용한 부분집합이다.
        메타는 LLM에 echo하지 않음 — frontend가 1차 메타와 합쳐 사용.
        """
        relevant_blocks = [b.model_dump(mode="json") for b in blocks]
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
            "포함한 충분한 설명 (ADR-0017). 이 노드가 **실행될 때** LLM에 주입되는 도메인 지침이다\n"
            "  - composer_instructions: 이 스킬의 COMPOSER.md 지침서 본문 (markdown 문자열, ADR-0024). "
            "워크플로우 **작성 에이전트(Composer)** 에 주입되어 '이 스킬을 쓰려면 어떤 노드를 어떻게 엮어야 "
            "하는가'를 지시한다. 예: 'LLM 노드 1개와 Email 발송 노드를 순서대로 배치하고, LLM 출력을 Email "
            "본문에 연결하라'. **필수 노드 종류와 연결 방식을 명시**해 Composer가 실행 가능한 워크플로우를 "
            "구성하도록 한다 (instructions와 소비처가 다름 — 실행 시 vs 생성 시)\n\n"
            "출력 전체는 **반드시 JSON** 형식입니다 (XML 금지). "
            "단 instructions / composer_instructions 필드의 *값*은 사람이 읽는 markdown 문자열입니다."
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
                "composer_instructions": (
                    "## 필수 노드\n이 스킬을 워크플로우에 쓰려면 다음 노드를 배치한다:\n"
                    "1. **Slack 메시지 발송 노드**(category=action, service=slack) — 매니저 채널 알림\n"
                    "## 연결\n환불 트리거의 refund_id·amount를 Slack 노드 입력으로 연결한다."
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
                "composer_instructions": {"type": "string"},
            },
            "required": ["inputs", "outputs", "required_connections", "instructions", "composer_instructions"],
        }

        payload = {
            "instruction": instruction,
            "personal_memory": memory_json,
            "document": {
                "file_name": file_name,
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
