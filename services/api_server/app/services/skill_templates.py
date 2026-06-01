"""default 스킬 템플릿(seed) 노출 + SOP DocumentBlock 합성 (REQ-010/013, 위저드 재설계).

스킬빌더 첫 화면에서 "문서가 없어요 → 직접 만들게요"를 고른 비전문가에게, 우리가 미리 만든
업종/직무 seed를 **SOP 문서 재료**로 제공한다(skill-builder-wizard-redesign.md D2). 사용자는 업종/직무
카드를 고르고, 서버는 해당 seed를 사람이 읽는 SOP markdown(DocumentBlock)으로 합성해 기존
`POST /skills/extract`(sop/extract) 경로에 그대로 투입한다 — 문서 경로와 추출 이후 완전히 동일하게 합류.

seed의 출처는 박아름 영역(`modules/ai_agent/seeds/`)이지만 여기서는 **읽기 전용**으로만 접근한다
(즉시-upsert use case는 건드리지 않음). 합성을 api_server(Composition Root)에 두어 skills-builder
계약을 무변경으로 유지한다(plan §7 — 크로스오너 마찰 최소).

⚠️ 크로스오너 동기화 주의(PR #280 리뷰 MED): seed 파일 경로(`{industry,functional_domain}_defaults/`)
와 키 스키마(`industry_code`/`domain_code` 등)에 직접 결합돼, 로딩·키 정규화 로직이 ai_agent의
`build_from_{industry_default,functional_domain}_use_case`와 일부 중복된다. seed 스키마/경로가
바뀌면 **api_server(여기) + ai_agent 양쪽을 함께 갱신**해야 한다(silent 런타임 파손 위험). 정공법은
ai_agent가 읽기전용 use case(ListDefaultTemplates / SynthesizeSopFromSeed)를 노출하고 api_server가
소비하는 것 — 박아름 복귀 후 후속 리팩터 권고.

seed 키 차이:
- industry_defaults/*.json: ``industry_code`` / ``industry_name`` / ``description``
- functional_domain_defaults/*.json: ``domain_code`` / ``domain_name`` / ``description``
→ ``{code, name, description, kind}``로 정규화해 노출한다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

import ai_agent
from common_schemas import ContentBlock, DocumentBlock, FileMeta
from common_schemas.enums import AnalysisStatus
from pydantic import BaseModel

# seed JSON 위치 — ai_agent 패키지를 기준으로 해석(상대 파일경로 하드코딩 회피). api_server는
# 이미 ai_agent를 설치/import하므로(__file__ 존재) 패키지 루트의 seeds/ 하위를 읽는다.
_SEEDS_ROOT = Path(ai_agent.__file__).resolve().parent / "seeds"
_INDUSTRY_DIR = _SEEDS_ROOT / "industry_defaults"
_FUNCTIONAL_DIR = _SEEDS_ROOT / "functional_domain_defaults"

# 합성 DocumentBlock의 document_id를 template_code에서 deterministic하게 생성(영속 X, 추적/로그용).
_TEMPLATE_DOC_NS = uuid5(UUID("00000000-0000-0000-0000-000000000000"), "workflow-automation.skill_template_sop")

TemplateKind = Literal["industry", "functional"]


class SkillTemplate(BaseModel):
    """default 위저드 카드 1건 — 업종 또는 직무 seed의 메타.

    code = seed의 industry_code/domain_code. extract 요청의 ``template_code``로 되돌아온다.
    """

    code: str
    name: str
    description: str
    kind: TemplateKind


def _read_seed(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _meta_from_seed(seed: dict, kind: TemplateKind) -> SkillTemplate | None:
    """seed dict → SkillTemplate. industry/functional 키 차이를 정규화."""
    if kind == "industry":
        code = seed.get("industry_code")
        name = seed.get("industry_name")
    else:
        code = seed.get("domain_code")
        name = seed.get("domain_name")
    description = seed.get("description", "")
    if not code or not name:
        return None
    return SkillTemplate(code=code, name=name, description=description, kind=kind)


@lru_cache(maxsize=1)
def list_templates() -> tuple[SkillTemplate, ...]:
    """사용 가능한 default 템플릿 전체(산업 + 직무) — code 정렬. seed 메타만 읽는 읽기 전용.

    seed 파일은 빌드 시 고정이라 캐시(lru_cache)한다. 깨진/메타 누락 seed는 조용히 건너뛴다
    (목록에서 빠질 뿐 — 부분 노출이 전체 실패보다 안전).
    """
    templates: list[SkillTemplate] = []
    for directory, kind in ((_INDUSTRY_DIR, "industry"), (_FUNCTIONAL_DIR, "functional")):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            seed = _read_seed(path)
            if seed is None:
                continue
            meta = _meta_from_seed(seed, kind)  # type: ignore[arg-type]
            if meta is not None:
                templates.append(meta)
    return tuple(templates)


def _find_seed_file(template_code: str) -> tuple[Path, TemplateKind] | None:
    """template_code → (seed 파일 경로, kind). 산업 우선 탐색, 없으면 직무."""
    for directory, kind in ((_INDUSTRY_DIR, "industry"), (_FUNCTIONAL_DIR, "functional")):
        candidate = directory / f"{template_code}.json"
        if candidate.is_file():
            return candidate, kind  # type: ignore[return-value]
    return None


def _node_to_sop_markdown(node: dict) -> str:
    """skill_node 1건 → 사람이 읽는 SOP 단락(markdown). LLM이 이 텍스트에서 SkillNode를 재추출한다.

    입력/출력은 JSON Schema의 property 이름만 풀어 노드의 작업 의도를 드러낸다(전체 스키마 dump는
    노이즈라 제외 — extract LLM이 어차피 스키마를 재생성).
    """
    inputs = node.get("inputs", {}).get("properties", {})
    outputs = node.get("outputs", {}).get("properties", {})
    connections = node.get("required_connections", [])
    lines = [
        node.get("description", ""),
        "",
        f"- 작업 유형: {node.get('category', '-')}",
        f"- 위험도: {node.get('risk_level', '-')}",
        f"- 필요 연동: {', '.join(connections) if connections else '없음'}",
        f"- 입력: {', '.join(inputs) if inputs else '없음'}",
        f"- 출력: {', '.join(outputs) if outputs else '없음'}",
    ]
    return "\n".join(lines)


def synthesize_sop_document(template_code: str, user_id: UUID) -> DocumentBlock | None:
    """template_code의 seed를 SOP DocumentBlock으로 합성. 미존재/깨짐이면 None.

    구조: 문서 제목(heading) + 개요(text) + skill_node마다 [작업명(heading) + 상세(text)].
    extract 엔진(`BuildFromSOPUseCase._build_prompt`)은 text/heading/table 블록의 content만
    LLM에 투입하므로, content에 읽을 수 있는 SOP 텍스트를 채우는 것이 핵심이다.
    """
    found = _find_seed_file(template_code)
    if found is None:
        return None
    path, kind = found
    seed = _read_seed(path)
    if seed is None:
        return None
    meta = _meta_from_seed(seed, kind)
    if meta is None:
        return None

    blocks: list[ContentBlock] = [
        ContentBlock(
            block_id=uuid5(_TEMPLATE_DOC_NS, f"{template_code}:title"),
            block_type="heading",
            content=f"{meta.name} 표준 업무 자동화 SOP",
            section_title=meta.name,
        ),
        ContentBlock(
            block_id=uuid5(_TEMPLATE_DOC_NS, f"{template_code}:overview"),
            block_type="text",
            content=meta.description,
        ),
    ]
    for idx, node in enumerate(seed.get("skill_nodes", [])):
        node_name = node.get("name", node.get("node_type", f"작업 {idx + 1}"))
        blocks.append(
            ContentBlock(
                block_id=uuid5(_TEMPLATE_DOC_NS, f"{template_code}:{idx}:heading"),
                block_type="heading",
                content=node_name,
                section_title=node_name,
            )
        )
        blocks.append(
            ContentBlock(
                block_id=uuid5(_TEMPLATE_DOC_NS, f"{template_code}:{idx}:body"),
                block_type="text",
                content=_node_to_sop_markdown(node),
            )
        )

    file_size = sum(len((b.content or "").encode("utf-8")) for b in blocks)
    return DocumentBlock(
        document_id=uuid5(_TEMPLATE_DOC_NS, template_code),
        user_id=user_id,
        file_meta=FileMeta(
            file_name=f"{meta.name} 표준 SOP.md",
            file_type="md",
            mime_type="text/markdown",
            file_size=file_size,
        ),
        blocks=blocks,
        analysis_status=AnalysisStatus.COMPLETED,
    )
