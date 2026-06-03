from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# 복합 레시피 키 (화이트리스트, 동적 체이닝 제외). 단일 의도 키는 IntentType.value를
# 그대로 쓰고, 복합만 별도 키를 둔다. 분류기(intent_analyzer)와 라우터(supervisor_router)가
# 공유하는 어휘라 최내곽 value_objects에 SSOT로 둔다 (매직 스트링 드리프트 방지).
RECIPE_SKILL_THEN_COMPOSE = "skill_then_compose"


class RouteTarget(str, Enum):
    """supervisor 루프가 한 홉에서 디스패치할 목적지.

    forward 스텝(레시피 큐)과 루프 북엔드(load/update_memory), 로컬 노드
    (general_chat/fast_response/finalize), 종료(DONE)를 모두 포괄한다.
    """

    LOAD_MEMORY = "load_memory"
    GENERAL_CHAT = "general_chat"
    FAST_RESPONSE = "fast_response"
    FINALIZE = "finalize"
    COMPOSER = "composer"
    SKILLS = "skills"
    UPDATE_MEMORY = "update_memory"
    DONE = "done"


@dataclass
class RoutePlan:
    """라우팅 레시피의 잔여 스텝 큐 + 커서.

    순수 VO — sub-agent 호출/IO 없음. 라우터 함수가 ``peek``으로 다음 forward
    스텝을 읽고, 루프가 스텝 완료 후 ``advance``한다. 복구 시 ``insert``로 대체
    스텝을 현재 커서에 끼워넣어 다음 ``peek``이 그것을 반환하게 한다.

    프레임/전송 스키마가 아니라 supervisor 내부 작업 객체라 frozen pydantic이
    아닌 mutable dataclass로 둔다 (커서 전진이 본질).
    """

    recipe_key: str
    steps: list[RouteTarget]
    cursor: int = 0

    def peek(self) -> RouteTarget | None:
        """현재 커서가 가리키는 스텝. 끝까지 소진했으면 None."""
        if self.cursor >= len(self.steps):
            return None
        return self.steps[self.cursor]

    def advance(self) -> None:
        """현재 스텝 완료 — 커서를 다음으로 전진."""
        self.cursor += 1

    def insert(self, target: RouteTarget) -> None:
        """현재 커서 위치에 대체 스텝 삽입 (복구 재시도용).

        다음 ``peek``이 삽입된 ``target``을 반환한다.
        """
        self.steps.insert(self.cursor, target)

    def is_done(self) -> bool:
        return self.cursor >= len(self.steps)

    def remaining(self) -> list[RouteTarget]:
        return self.steps[self.cursor:]
