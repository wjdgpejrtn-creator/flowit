"""storage mappers — 속성 접근 시점 지연 로드(PEP 562 `__getattr__`).

일부 매퍼는 자신이 변환하는 도메인 모듈을 import한다(`AgentMemoryMapper`→`ai_agent`,
`marketplace_skill_mapper`/`skill_mapper`→`skills_marketplace`). 패키지 import 시점에
14개를 전부 eager import하면, 그 도메인이 설치되지 않은 실행 환경(예: execution_engine
worker 이미지엔 `ai_agent`·`skills_marketplace` 미설치)에서
`from ..mappers.document_mapper import DocumentMapper`처럼 무해한 매퍼 하나만 쓰려 해도
`storage/mappers/__init__`이 통째로 실행되며 `ModuleNotFoundError`로 cascade 크래시한다.
(2026-05-29 문서 analyze worker 사고 — #236(repositories)·#238(adapters)에 이은 세 번째
지점. `PgDocumentRepository`가 `from ..mappers.document_mapper import DocumentMapper`로
이 `__init__`을 건드린다.)

→ 실제 그 클래스를 속성으로 접근할 때까지 import를 미룬다. `from storage.mappers import
DocumentMapper` / `from storage.mappers.document_mapper import DocumentMapper` 모두 그대로
동작하며, ai_agent/skills_marketplace를 요구하는 매퍼는 실제 참조 시에만 로드된다.
"""
from importlib import import_module
from typing import TYPE_CHECKING

# 공개 이름 → 정의 모듈 경로(상대) 매핑. 새 mapper 추가 시 이 `_LAZY` + 아래 TYPE_CHECKING
# 블록 + `__all__` 세 곳을 함께 갱신.
_LAZY: dict[str, str] = {
    "AgentMemoryMapper": ".agent_memory_mapper",
    "CredentialMapper": ".credential_mapper",
    "DocumentMapper": ".document_mapper",
    "ExecutionMapper": ".execution_mapper",
    "ExecutionRow": ".execution_mapper",
    "CompanySkillMapper": ".marketplace_skill_mapper",
    "PersonalSkillMapper": ".marketplace_skill_mapper",
    "SkillApprovalMapper": ".marketplace_skill_mapper",
    "TeamSkillMapper": ".marketplace_skill_mapper",
    "NodeDefinitionMapper": ".node_definition_mapper",
    "OAuthConnectionMapper": ".oauth_connection_mapper",
    "SessionMapper": ".session_mapper",
    "Skill": ".skill_mapper",
    "SkillMapper": ".skill_mapper",
    "StorageObjectMapper": ".storage_object_mapper",
    "ToolExecutionMapper": ".tool_execution_mapper",
    "UserMapper": ".user_mapper",
    "WorkflowMapper": ".workflow_mapper",
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
    "AgentMemoryMapper",
    "CredentialMapper",
    "DocumentMapper",
    "ExecutionMapper",
    "ExecutionRow",
    "CompanySkillMapper",
    "PersonalSkillMapper",
    "SkillApprovalMapper",
    "TeamSkillMapper",
    "NodeDefinitionMapper",
    "OAuthConnectionMapper",
    "SessionMapper",
    "Skill",
    "SkillMapper",
    "StorageObjectMapper",
    "ToolExecutionMapper",
    "UserMapper",
    "WorkflowMapper",
]

# 정적 타입 검사기(mypy/pyright)는 지연 로드를 따라가지 못하므로 명시적 재노출.
# 위 `_LAZY`와 동기 유지(새 mapper 추가 시 함께 갱신).
if TYPE_CHECKING:
    from .agent_memory_mapper import AgentMemoryMapper
    from .credential_mapper import CredentialMapper
    from .document_mapper import DocumentMapper
    from .execution_mapper import ExecutionMapper, ExecutionRow
    from .marketplace_skill_mapper import (
        CompanySkillMapper,
        PersonalSkillMapper,
        SkillApprovalMapper,
        TeamSkillMapper,
    )
    from .node_definition_mapper import NodeDefinitionMapper
    from .oauth_connection_mapper import OAuthConnectionMapper
    from .session_mapper import SessionMapper
    from .skill_mapper import Skill, SkillMapper
    from .storage_object_mapper import StorageObjectMapper
    from .tool_execution_mapper import ToolExecutionMapper
    from .user_mapper import UserMapper
    from .workflow_mapper import WorkflowMapper
