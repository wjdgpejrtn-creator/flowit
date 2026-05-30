"""storage 패키지 공개 API — 지연 로드(PEP 562 `__getattr__`).

`from storage import PgXxxRepository` 형태를 그대로 지원하되, import 시점이 아닌
속성 접근 시점에 해당 repository만 로드한다. eager import 시 `PgAgentMemoryRepository`가
`ai_agent`를 끌어와, ai_agent 미설치 환경(worker)에서 storage를 건드리는 모든 코드가
cascade 크래시했던 문제를 차단한다 (`repositories/__init__` 주석 참조).
"""
from importlib import import_module
from typing import TYPE_CHECKING

# 패키지 top-level(`from storage import ...`)로 재노출하는 repository.
# `repositories/__init__`의 `_LAZY`(12개)와 달리 여기는 10개 — `PgMarketplaceSkillRepository`,
# `PgUserRepository`는 의도적으로 top-level 재노출 제외(이 PR 이전 behavior 그대로 보존).
# 이 둘은 `from storage.repositories import ...`로만 import한다.
# 새 repository 추가 시 세 곳을 함께 갱신: `repositories/__init__`의 `_LAZY` + 아래 TYPE_CHECKING
# 블록 + (top-level 노출이 필요하면) 이 `_REEXPORT`.
_REEXPORT = frozenset(
    {
        "PgAgentMemoryRepository",
        "PgCredentialRepository",
        "PgDocumentRepository",
        "PgExecutionRepository",
        "PgNodeDefinitionRepository",
        "PgOAuthRepository",
        "PgSessionRepository",
        "PgSkillRepository",
        "PgToolExecutionRepository",
        "PgWorkflowRepository",
    }
)


def __getattr__(name: str):
    if name in _REEXPORT:
        return getattr(import_module(".repositories", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "PgAgentMemoryRepository",
    "PgCredentialRepository",
    "PgDocumentRepository",
    "PgExecutionRepository",
    "PgNodeDefinitionRepository",
    "PgOAuthRepository",
    "PgSessionRepository",
    "PgSkillRepository",
    "PgToolExecutionRepository",
    "PgWorkflowRepository",
]

# 정적 타입 검사기용 명시적 재노출 — `_REEXPORT`와 동기 유지(새 repository 추가 시 함께 갱신).
if TYPE_CHECKING:
    from .repositories import (
        PgAgentMemoryRepository,
        PgCredentialRepository,
        PgDocumentRepository,
        PgExecutionRepository,
        PgNodeDefinitionRepository,
        PgOAuthRepository,
        PgSessionRepository,
        PgSkillRepository,
        PgToolExecutionRepository,
        PgWorkflowRepository,
    )
