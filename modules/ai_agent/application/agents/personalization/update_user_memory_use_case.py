"""Personalization — 워크플로우 완료 후 사용자 memory 갱신.

PHASE 1: Debounce + Incremental Save (LLM 패턴 추출).
PHASE 2 (신정혜 협의 후): turn_count/workflow 파라미터 추가, 저장 조건 강화, cleanup lifecycle.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from ....domain.entities.memory_file import MemoryFile, MemoryFileRef, MemoryFileType
from ....domain.ports.llm_port import LLMPort
from ....domain.ports.personal_memory_store import PersonalMemoryStore

_DEFAULT_DEBOUNCE = timedelta(minutes=30)


class _MemoryUpdateSpec(BaseModel):
    action: Literal["create", "update", "skip"]
    filename: str
    name: str
    description: str
    memory_type: MemoryFileType
    body: str


class _MemoryUpdateResult(BaseModel):
    updates: list[_MemoryUpdateSpec]


def _build_prompt(session_summary: str, existing: list[MemoryFile]) -> str:
    existing_md = "\n\n".join(
        f"### {f.filename}\ntype: {f.memory_type}\n{f.body}" for f in existing
    ) or "(없음)"
    return (
        "당신은 사용자 개인 워크플로우 패턴을 관리하는 메모리 에이전트입니다.\n\n"
        "## 현재 저장된 메모리\n"
        f"{existing_md}\n\n"
        "## 이번 세션 요약\n"
        f"{session_summary}\n\n"
        "## 지시사항\n"
        "위 세션 요약에서 사용자의 워크플로우 패턴/선호도/피드백을 추출하세요.\n"
        "각 항목에 대해 아래 중 하나를 선택하세요:\n"
        "- action=create: 새 .md 파일 생성\n"
        "- action=update: 기존 파일 내용 갱신\n"
        "- action=skip: 변경 없음\n\n"
        "memory_type은 user(역할/목표)/feedback(패턴/피드백)/project(진행중 작업)/reference(참조 링크) 중 하나.\n"
        "filename은 snake_case.md 형식. body는 한국어로 작성.\n"
        "의미 있는 새 정보가 없으면 모든 항목을 skip으로 반환하세요."
    )


class UpdateUserMemoryUseCase:
    """LLM이 세션 요약에서 패턴 추출 → 변경된 .md만 선택적으로 저장.

    Debounce: 마지막 저장으로부터 debounce_window 미만이면 저장 건너뜀.
    Incremental Save: 변경된 항목만 GCS에 write (MEMORY.md도 변경 시만 갱신).
    """

    def __init__(
        self,
        memory_store: PersonalMemoryStore,
        llm: LLMPort,
        debounce_window: timedelta = _DEFAULT_DEBOUNCE,
    ) -> None:
        self._store = memory_store
        self._llm = llm
        self._debounce_window = debounce_window
        self._last_updated: dict[UUID, datetime] = {}

    async def execute(self, user_id: UUID, session_summary: str) -> bool:
        """반환: True=저장됨, False=debounce로 건너뜀."""
        now = datetime.now(timezone.utc)
        last = self._last_updated.get(user_id)
        if last is not None and (now - last) < self._debounce_window:
            return False

        refs = await self._store.load_index(user_id)
        existing: dict[str, MemoryFile] = {}
        for ref in refs:
            try:
                existing[ref.filename] = await self._store.load_file(user_id, ref.filename)
            except FileNotFoundError:
                pass

        prompt = _build_prompt(session_summary, list(existing.values()))
        result: _MemoryUpdateResult = await self._llm.generate_structured(prompt, _MemoryUpdateResult)

        index_map: dict[str, MemoryFileRef] = {ref.filename: ref for ref in refs}
        changed = False
        for spec in result.updates:
            if spec.action == "skip":
                continue
            file = MemoryFile(
                filename=spec.filename,
                name=spec.name,
                description=spec.description,
                memory_type=spec.memory_type,
                body=spec.body,
            )
            await self._store.save_file(user_id, file)
            index_map[spec.filename] = MemoryFileRef(
                filename=spec.filename,
                name=spec.name,
                description=spec.description,
            )
            changed = True

        if changed:
            await self._store.save_index(user_id, list(index_map.values()))
            self._last_updated[user_id] = now

        return changed
