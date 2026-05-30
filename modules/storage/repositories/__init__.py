"""storage repositories — 속성 접근 시점 지연 로드(PEP 562 `__getattr__`).

각 repository 구현체는 자신이 매핑하는 도메인 모듈(auth / ai_agent / nodes_graph /
skills_marketplace / doc_parser ...)을 import한다. 패키지 import 시점에 12개를 전부
eager import하면, 일부 도메인 모듈이 설치되지 않은 실행 환경(예: execution_engine
worker 이미지에는 `ai_agent` 미설치)에서 `from storage.adapters.gcs_adapter import ...`
처럼 storage를 건드리기만 해도 `storage/__init__` → 이 파일이 통째로 import되며
`ModuleNotFoundError: No module named 'ai_agent'`로 cascade 크래시한다.
(2026-05-29 문서 analyze worker 사고 — `PgAgentMemoryRepository`가 `ai_agent` 의존.)

→ 그래서 실제 그 클래스를 쓰는 쪽에서 속성으로 접근할 때까지 import를 미룬다.
`from storage.repositories import PgDocumentRepository`는 그대로 동작하며, ai_agent를
요구하는 `PgAgentMemoryRepository`는 그것을 실제로 참조할 때만 로드된다.
"""
from importlib import import_module
from typing import TYPE_CHECKING

# 공개 이름 → 정의 모듈 경로(상대) 매핑. 새 repository 추가 시 세 곳을 함께 갱신:
# 이 `_LAZY` + 아래 TYPE_CHECKING 블록 + (top-level 노출이 필요하면) `storage/__init__`의 `_REEXPORT`.
_LAZY: dict[str, str] = {
    "PgAgentMemoryRepository": ".pg_agent_memory_repository",
    "PgCredentialRepository": ".pg_credential_repository",
    "PgDocumentRepository": ".pg_document_repository",
    "PgExecutionRepository": ".pg_execution_repository",
    "PgMarketplaceSkillRepository": ".pg_marketplace_skill_repository",
    "PgNodeDefinitionRepository": ".pg_node_definition_repository",
    "PgOAuthRepository": ".pg_oauth_repository",
    "PgSessionRepository": ".pg_session_repository",
    "PgSkillRepository": ".pg_skill_repository",
    "PgToolExecutionRepository": ".pg_tool_execution_repository",
    "PgUserRepository": ".pg_user_repository",
    "PgWorkflowRepository": ".pg_workflow_repository",
}


def __getattr__(name: str):
    module_path = _LAZY.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_path, __name__)
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "PgAgentMemoryRepository",
    "PgCredentialRepository",
    "PgDocumentRepository",
    "PgExecutionRepository",
    "PgMarketplaceSkillRepository",
    "PgNodeDefinitionRepository",
    "PgOAuthRepository",
    "PgSessionRepository",
    "PgSkillRepository",
    "PgToolExecutionRepository",
    "PgUserRepository",
    "PgWorkflowRepository",
]

# 정적 타입 검사기(mypy/pyright)는 지연 로드를 따라가지 못하므로 명시적 재노출.
# 위 `_LAZY`와 동기 유지(새 repository 추가 시 함께 갱신, top-level 노출은 `storage/__init__`도).
if TYPE_CHECKING:
    from .pg_agent_memory_repository import PgAgentMemoryRepository
    from .pg_credential_repository import PgCredentialRepository
    from .pg_document_repository import PgDocumentRepository
    from .pg_execution_repository import PgExecutionRepository
    from .pg_marketplace_skill_repository import PgMarketplaceSkillRepository
    from .pg_node_definition_repository import PgNodeDefinitionRepository
    from .pg_oauth_repository import PgOAuthRepository
    from .pg_session_repository import PgSessionRepository
    from .pg_skill_repository import PgSkillRepository
    from .pg_tool_execution_repository import PgToolExecutionRepository
    from .pg_user_repository import PgUserRepository
    from .pg_workflow_repository import PgWorkflowRepository
