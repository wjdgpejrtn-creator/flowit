"""Personalization — 워크플로우 완료 후 사용자 memory 갱신.

LLM이 session_summary + workflow에서 패턴을 추출하여 GCS .md 파일로 저장/갱신.
MEMORY.md 인덱스도 함께 갱신한다.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from common_schemas import WorkflowSchema
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from pydantic import BaseModel

from ai_agent.domain.entities.personal_skill import PersonalSkill
from ai_agent.domain.ports.llm_port import LLMPort
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore

_EXTRACT_PROMPT = """\
사용자 워크플로우 세션이 완료되었습니다.
아래 세션 요약과 완성된 워크플로우를 분석하여 사용자 패턴을 추출하세요.

세션 요약:
{session_summary}

완성된 워크플로우:
{workflow_json}

추출 기준:
- user: 사용자 역할, 목표, 도메인 지식
- feedback: 사용자가 수정하거나 선호한 방향
- project: 진행 중인 프로젝트나 업무 컨텍스트
- reference: 자주 참조하는 시스템, 도구, 데이터 소스

패턴이 없으면 빈 리스트를 반환하세요.
각 패턴의 body는 "WHY: ...\\nHow to apply: ..." 형식으로 작성하세요.
"""


class _SkillItem(BaseModel):
    name: str
    description: str
    skill_type: Literal["user", "feedback", "project", "reference"]
    body: str


class _SkillExtraction(BaseModel):
    skills: list[_SkillItem]


class UpdateUserMemoryUseCase:
    def __init__(
        self,
        memory_store: PersonalMemoryStore,
        llm: LLMPort,
        embedder: EmbedderPort,
    ) -> None:
        self._store = memory_store
        self._llm = llm
        self._embedder = embedder

    async def execute(
        self,
        user_id: UUID,
        session_summary: dict,
        workflow: WorkflowSchema,
    ) -> None:
        prompt = _EXTRACT_PROMPT.format(
            session_summary=session_summary,
            workflow_json=workflow.model_dump_json(indent=2),
        )
        extraction = await self._llm.generate_structured(prompt, _SkillExtraction)

        for item in extraction.skills:
            embedding = await self._embedder.embed(
                f"{item.name} {item.description} {item.body}"
            )
            skill = PersonalSkill(
                user_id=user_id,
                skill_type=item.skill_type,
                name=item.name,
                description=item.description,
                body=item.body,
                embedding=embedding,
            )
            await self._store.save_entry(user_id, skill)

        if extraction.skills:
            await self._update_index(user_id, extraction.skills)

    async def _update_index(self, user_id: UUID, new_items: list[_SkillItem]) -> None:
        current = await self._store.load_index(user_id)
        lines = current.splitlines() if current else ["# Memory Index", ""]
        existing_names = {
            line.split("](")[0].lstrip("- [")
            for line in lines
            if line.startswith("- [")
        }
        for item in new_items:
            if item.name not in existing_names:
                lines.append(f"- [{item.name}]({item.name}.md) — {item.description}")
        await self._store.save_index(user_id, "\n".join(lines))
