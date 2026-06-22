"""storage adapters — 속성 접근 시점 지연 로드(PEP 562 `__getattr__`).

`GcsSkillDocumentStore`는 `skills_marketplace` 도메인을 import한다. 패키지 import 시점에
4개 어댑터를 전부 eager import하면, `skills_marketplace`가 설치되지 않은 실행 환경(예:
execution_engine worker 이미지)에서 `from storage.adapters.gcs_adapter import GCSAdapter`
처럼 다른 어댑터만 쓰려 해도 `storage/adapters/__init__`이 통째로 실행되며
`ModuleNotFoundError: No module named 'skills_marketplace'`로 cascade 크래시한다.
(2026-05-29 문서 analyze worker 사고 — #236이 `repositories/__init__`의 동일 패턴을
고쳤으나 이 `adapters/__init__`은 누락돼 있었다. `document_tasks._analyze`가
`from storage.adapters.gcs_adapter import GCSAdapter` 하는 순간 재발.)

→ 실제 그 클래스를 속성으로 접근할 때까지 import를 미룬다. `from storage.adapters import
GCSAdapter` / `from storage.adapters.gcs_adapter import GCSAdapter` 모두 그대로 동작하며,
skills_marketplace를 요구하는 `GcsSkillDocumentStore`는 실제 참조 시에만 로드된다.
"""
from importlib import import_module
from typing import TYPE_CHECKING

# 공개 이름 → 정의 모듈 경로(상대) 매핑. 새 adapter 추가 시 이 `_LAZY` + 아래 TYPE_CHECKING
# 블록 + `__all__` 세 곳을 함께 갱신.
_LAZY: dict[str, str] = {
    "ClamAVAdapter": ".clamav_adapter",
    "GCSAdapter": ".gcs_adapter",
    "GcsSkillDocumentStore": ".gcs_skill_document_store",
    "LocalStorageAdapter": ".local_storage_adapter",
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
    "ClamAVAdapter",
    "GCSAdapter",
    "GcsSkillDocumentStore",
    "LocalStorageAdapter",
]

# 정적 타입 검사기(mypy/pyright)는 지연 로드를 따라가지 못하므로 명시적 재노출.
# 위 `_LAZY`와 동기 유지(새 adapter 추가 시 함께 갱신).
if TYPE_CHECKING:
    from .clamav_adapter import ClamAVAdapter
    from .gcs_adapter import GCSAdapter
    from .gcs_skill_document_store import GcsSkillDocumentStore
    from .local_storage_adapter import LocalStorageAdapter
