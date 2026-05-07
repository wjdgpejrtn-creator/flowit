# Phase 3 — Adapter Layer (Core)

> **대상 경로**: `modules/toolset/adapters/`
> **포함 파일**: `tool_registry_adapter.py`, `secure_connector.py`, `state_manager.py`
> **허용 import**: 외부 SDK, 프레임워크, `auth.domain.services` (CLAUDE.md 허용 목록)

---

## 3-1. `adapters/tool_registry_adapter.py`

**역할**: `ToolRegistry` Port의 인메모리 구현체.

```python
from __future__ import annotations

from common_schemas.exceptions import NotFoundError

from ..domain.entities.base_tool import BaseTool
from ..domain.entities.tool_metadata import ToolMetadata
from ..domain.exceptions import ConflictError
from ..domain.ports.tool_registry import ToolRegistry


class ToolRegistryAdapter(ToolRegistry):
    """
    ToolRegistry의 인메모리 구현체.

    앱 시작 시 8개 도구 등록 (DI 컨테이너에서 호출).
    싱글턴으로 관리 — DI 컨테이너에서 한 번 생성 후 재사용.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._metadata: dict[str, ToolMetadata] = {}

    def get(self, tool_name: str) -> BaseTool:
        if tool_name not in self._tools:
            raise NotFoundError(
                message=f"Tool '{tool_name}' is not registered. "
                        f"Available: {list(self._tools.keys())}",
                code="E_NODE_TYPE_MISMATCH",
            )
        return self._tools[tool_name]

    def list_all(self) -> list[ToolMetadata]:
        return list(self._metadata.values())

    def list_by_category(self, category: str) -> list[ToolMetadata]:
        return [m for m in self._metadata.values() if m.category == category]

    def register_tool(
        self,
        tool: BaseTool,
        tool_id: UUID,
        version: str,
        category: str,
        overwrite: bool = True,
    ) -> None:
        """
        도구 등록.

        Args:
            overwrite: False면 이미 등록된 tool_name 시 ConflictError 발생
        """
        if not overwrite and tool.name in self._tools:
            raise ConflictError(
                message=f"Tool '{tool.name}' is already registered.",
                code="E_DUPLICATE_ID",
            )
        self._tools[tool.name] = tool
        self._metadata[tool.name] = ToolMetadata.from_tool(
            tool, tool_id=tool_id, version=version, category=category
        )

    def register_bulk(self, tools: list[tuple[BaseTool, UUID, str, str]]) -> None:
        """일괄 등록. (tool, tool_id, version, category) 튜플 리스트."""
        for tool, tool_id, version, category in tools:
            self.register_tool(tool, tool_id, version, category)

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistryAdapter(tools={list(self._tools.keys())})"
```

---

## 3-2. `adapters/secure_connector.py`

**역할**: `SecureConnectorPort` 구현체. `auth.domain.services.CredentialInjectionService`를 DI로 주입받아 복호화 처리.

```python
from __future__ import annotations

import logging
from uuid import UUID

from common_schemas.security import PlaintextCredential

from ..domain.exceptions import CredentialError
from ..domain.ports.secure_connector_port import SecureConnectorPort

logger = logging.getLogger(__name__)


class SecureConnector(SecureConnectorPort):
    """
    SecureConnectorPort 구현체.

    auth.domain.services.CredentialInjectionService를 통해
    credential_id를 복호화하여 PlaintextCredential을 반환한다.

    CLAUDE.md 허용 import:
        from auth.domain.services import CredentialInjectionService
        → inject(credential_id: UUID, node_id: UUID) → PlaintextCredential

    보안 원칙:
    - 활성 credential은 _active dict에 최단 시간만 보관
    - release_credential() 호출 시 _active에서 즉시 제거
    - release 실패 시 로그만 남기고 예외 미발생 (best-effort)

    ⚠️ 협의 필요 (REQ-002 박아름):
    - inject()의 node_id 파라미터 처리 방식 확인 필요
    - toolset이 node_id를 갖지 않는 경우 처리 방안
    """

    def __init__(
        self,
        inject_credential_service: object,
        node_id: UUID | None = None,
    ) -> None:
        """
        Args:
            inject_credential_service: auth.domain.services.CredentialInjectionService
                타입 힌트를 object로 두는 이유:
                toolset → auth 직접 import는 adapters 레이어에서만 허용이나,
                런타임 DI 주입 시 타입 검사를 피하기 위해 duck-typing.
            node_id: 실행 중인 노드 ID. 없으면 UUID(0) 사용.
        """
        self._inject = inject_credential_service
        self._node_id = node_id or UUID(int=0)
        # credential_id(str) → PlaintextCredential 매핑 (활성 상태만 보관)
        self._active: dict[str, PlaintextCredential] = {}

    async def acquire_credential(
        self,
        credential_id: str,
        service: str,
    ) -> PlaintextCredential:
        """
        CredentialInjectionService.inject()를 통해 복호화된 credential 획득.

        Raises:
            CredentialError: 복호화 실패 또는 credential 미존재
        """
        try:
            # inject(credential_id: UUID, node_id: UUID) → PlaintextCredential
            credential: PlaintextCredential = await self._inject.inject(
                UUID(credential_id),
                self._node_id,
            )
        except Exception as e:
            raise CredentialError(
                message=f"Failed to acquire credential '{credential_id}': {e}",
                code="CREDENTIAL_ERROR",
            ) from e

        self._active[credential_id] = credential
        return credential

    async def release_credential(self, credential_id: str) -> None:
        """_active에서 credential 제거. 실패 시 로그만 남김 (best-effort)."""
        try:
            self._active.pop(credential_id, None)
        except Exception:
            logger.warning(
                "Failed to release credential '%s' from active store.",
                credential_id,
            )
```

**협의 포인트 (REQ-002 박아름):**
- `CredentialInjectionService.inject(credential_id: UUID, node_id: UUID)` — `node_id`는 어떤 값 사용?
- execution-engine에서 `ExecuteToolUseCase` 호출 시 현재 노드 ID를 `context`에 포함시키는 방안 검토
- 대안: `node_id=None` 허용하도록 inject 시그니처 수정 요청

---

## 3-3. `adapters/state_manager.py`

**역할**: 도구 실행 상태 추적. Redis 우선, 장애 시 PostgreSQL fallback.

```python
from __future__ import annotations

import json
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Redis key 패턴
_KEY_PATTERN = "session:{session_id}:tool:{tool_name}:{purpose}"

# TTL 설정
_DEFAULT_TTL = timedelta(minutes=30)   # idle TTL
_MAX_TTL = timedelta(hours=24)         # 최대 TTL


class StateManager:
    """
    도구 실행 상태 추적기.

    Redis 우선, 장애 시 PostgreSQL fallback (Degraded Mode).
    _use_redis 플래그: 첫 Redis 예외 발생 시 False로 전환, 이후 PG 사용.

    Redis key 패턴:
        session:{session_id}:tool:{tool_name}:{purpose}

    TTL:
        - idle: 30분
        - max: 24시간 (추후 session TTL과 동기화 — REQ-002 확인 필요)
    """

    def __init__(
        self,
        redis_client: object,              # redis.asyncio.Redis
        db_session: object | None = None,  # AsyncSession (fallback)
    ) -> None:
        self._redis = redis_client
        self._db = db_session
        self._use_redis = True

    def _make_key(
        self,
        session_id: str,
        tool_name: str,
        purpose: str = "state",
    ) -> str:
        return _KEY_PATTERN.format(
            session_id=session_id,
            tool_name=tool_name,
            purpose=purpose,
        )

    async def set_state(
        self,
        session_id: str,
        tool_name: str,
        state: dict,
        purpose: str = "state",
    ) -> None:
        """
        도구 실행 상태 저장.

        Args:
            session_id: 사용자 세션 ID
            tool_name: 도구 식별자 (예: "google_drive")
            state: 저장할 상태 딕셔너리
            purpose: 상태 종류 구분자 (기본: "state")
        """
        key = self._make_key(session_id, tool_name, purpose)
        value = json.dumps(state)

        if self._use_redis:
            try:
                await self._redis.setex(key, _DEFAULT_TTL, value)
                return
            except Exception as e:
                logger.warning("Redis unavailable, falling back to DB: %s", e)
                self._use_redis = False

        if self._db:
            await self._db_set_state(session_id, tool_name, purpose, state)

    async def get_state(
        self,
        session_id: str,
        tool_name: str,
        purpose: str = "state",
    ) -> dict | None:
        """
        저장된 도구 실행 상태 조회.

        Returns:
            저장된 상태 딕셔너리, 없으면 None
        """
        key = self._make_key(session_id, tool_name, purpose)

        if self._use_redis:
            try:
                value = await self._redis.get(key)
                return json.loads(value) if value else None
            except Exception as e:
                logger.warning("Redis get failed, falling back to DB: %s", e)
                self._use_redis = False

        if self._db:
            return await self._db_get_state(session_id, tool_name, purpose)

        return None

    async def clear_state(
        self,
        session_id: str,
        tool_name: str,
        purpose: str = "state",
    ) -> None:
        """도구 실행 상태 삭제."""
        key = self._make_key(session_id, tool_name, purpose)

        if self._use_redis:
            try:
                await self._redis.delete(key)
                return
            except Exception as e:
                logger.warning("Redis delete failed: %s", e)

        if self._db:
            await self._db_clear_state(session_id, tool_name, purpose)

    async def _db_set_state(
        self,
        session_id: str,
        tool_name: str,
        purpose: str,
        state: dict,
    ) -> None:
        """PostgreSQL fallback 저장 — REQ-001 황대원과 테이블 스키마 협의 후 구현."""
        # TODO: PostgreSQL 구현 (REQ-001 스키마 확정 후)
        logger.info("DB fallback set_state: %s/%s/%s", session_id, tool_name, purpose)

    async def _db_get_state(
        self,
        session_id: str,
        tool_name: str,
        purpose: str,
    ) -> dict | None:
        """PostgreSQL fallback 조회."""
        # TODO: PostgreSQL 구현 (REQ-001 스키마 확정 후)
        return None

    async def _db_clear_state(
        self,
        session_id: str,
        tool_name: str,
        purpose: str,
    ) -> None:
        """PostgreSQL fallback 삭제."""
        # TODO: PostgreSQL 구현 (REQ-001 스키마 확정 후)
        pass
```

---

## 3-4. `adapters/__init__.py`

```python
from .tool_registry_adapter import ToolRegistryAdapter
from .secure_connector import SecureConnector
from .state_manager import StateManager

__all__ = ["ToolRegistryAdapter", "SecureConnector", "StateManager"]
```

---

## 확인 체크리스트

- [ ] `tool_registry_adapter.py`: `get_tool()` — 미등록 시 Available 목록 포함 에러 메시지
- [ ] `tool_registry_adapter.py`: `list_metadata()` 구현 (ListToolsUseCase에서 사용)
- [ ] `tool_registry_adapter.py`: `register_bulk()` 8개 도구 일괄 등록
- [ ] `secure_connector.py`: `release_credential()` best-effort, 예외 미발생
- [ ] `secure_connector.py`: `CredentialInjectionService.inject(UUID(credential_id), node_id)` 호출 확인
- [ ] `secure_connector.py`: REQ-002 박아름 — `node_id` 처리 방식 사전 확인 필요
- [ ] `state_manager.py`: Redis → PostgreSQL fallback 전환 로직
- [ ] `state_manager.py`: `_KEY_PATTERN` key 형식 = `session:{sid}:tool:{name}:{purpose}`
- [ ] `state_manager.py`: PostgreSQL TODO 주석 유지 (REQ-001 확정 후 구현)
- [ ] REQ-001 황대원: PostgreSQL fallback 테이블 스키마 협의
