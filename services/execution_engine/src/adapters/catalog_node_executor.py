from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any

from common_schemas import NodeContext
from common_schemas.workflow import NodeConfig, NodeInstance

from ..domain.ports.node_executor_port import NodeExecutorPort

if TYPE_CHECKING:
    from skills_marketplace.domain.ports.skill_document_store import SkillDocumentStore

logger = logging.getLogger(__name__)

# container가 주입하는 credential 해결기 팩토리. 호출 시 async context manager를
# 반환하며, with 블록 안에서 `inject(credential_id, node_id) -> PlaintextCredential`을
# 노출하는 서비스(auth `CredentialInjectionService`)를 yield한다.
CredentialServiceFactory = Callable[[], AbstractAsyncContextManager[Any]]


class CatalogNodeExecutor(NodeExecutorPort):
    """워크플로우 노드 실행 — node_type → `BaseNode.process()` 직접 호출 (ADR-0018).

    ADR-0014 경로 A(`ToolsetExecutor` 위임)를 폐기하고, 53종 노드를 동일하게
    `BaseNode.process(input, context)`로 실행한다. sync Celery worker ↔ async
    `process()` 브리지는 `asyncio.run()`으로 처리한다.

    Phase 2b: `node.credential_id`가 있으면 실행 직전 `CredentialInjectionService`로
    connection 토큰을 해결해 `NodeContext.connection_token`에 적재하고, `process()`
    종료 후 평문 토큰을 `wipe()`한다 (ADR-0018 Decision 5·6).
    """

    def __init__(
        self,
        node_classes: dict[str, type],
        credential_service_factory: CredentialServiceFactory | None = None,
        skill_document_store: SkillDocumentStore | None = None,
    ) -> None:
        self._node_classes = node_classes
        self._credential_service_factory = credential_service_factory
        self._skill_document_store = skill_document_store

    def execute(
        self,
        node: NodeInstance,
        config: NodeConfig,
        inputs: dict[str, Any],
        context: NodeContext,
    ) -> dict[str, Any]:
        node_class = self._node_classes.get(config.node_type)
        if node_class is None:
            raise ValueError(f"카탈로그 미등록 node_type: {config.node_type}")

        node_instance = node_class()
        node_input = self._build_input(node_instance, node, inputs)

        logger.info(
            "CatalogNodeExecutor: node_type=%s, node=%s", config.node_type, node.instance_id
        )
        # credential 해결(async DB)과 process()(async)를 단일 이벤트 루프로 묶는다.
        return asyncio.run(self._run(node_instance, node_input, node, config, context))

    async def _run(
        self,
        node_instance: Any,
        node_input: Any,
        node: NodeInstance,
        config: NodeConfig,
        context: NodeContext,
    ) -> dict[str, Any]:
        injected: list[Any] = []
        try:
            if node.credential_ids:
                # 멀티 provider 바인딩 — provider별 토큰을 connection_tokens에 적재 (REQ-012).
                for service, cred_id in node.credential_ids.items():
                    cred = await self._inject(cred_id, node.node_id)
                    injected.append(cred)
                    context.connection_tokens[service] = cred.value
                # 단일 connection이면 primary(connection_token)도 채워 단일 노드 하위호환 유지.
                if len(injected) == 1:
                    context.connection_token = injected[0].value
            elif node.credential_id is not None:
                # legacy 단일 바인딩 — provider 미지정(주입 시 CredentialInjectionService가
                # node 정의 required_connections로 service 매칭 검증).
                cred = await self._inject(node.credential_id, node.node_id)
                injected.append(cred)
                context.connection_token = cred.value
            # 바인딩된 SkillDocument(도메인 지침서)를 system 프롬프트에 주입 (REQ-013).
            # skill은 선택적 보강이라 미배선/실패/미존재는 무주입 degrade(실행 막지 않음).
            if node.skill_id is not None and self._supports_system(node_instance, config):
                node_input = await self._inject_skill(node_input, node.skill_id)
            output = await node_instance.process(node_input, context)
            return self._to_dict(output)
        finally:
            # 평문 connection 토큰을 노드 실행 종료 즉시 제거 (ADR-0018 Decision 5).
            for cred in injected:
                cred.wipe()
            context.wipe()

    async def _inject(self, credential_id: Any, node_id: Any) -> Any:
        if self._credential_service_factory is None:
            raise RuntimeError(
                f"노드 {node_id}가 credential을 요구하지만 credential_service_factory가 "
                "주입되지 않았다 (container.py 배선 확인)."
            )
        async with self._credential_service_factory() as service:
            return await service.inject(credential_id, node_id)

    async def _inject_skill(self, node_input: Any, skill_id: Any) -> Any:
        """바인딩된 SkillDocument의 instructions를 노드 system 프롬프트에 주입.

        skill은 선택적 보강이므로 store 미배선·조회 실패·미존재는 모두 무주입으로
        degrade한다 (credential과 달리 RuntimeError를 던지지 않는다 — 지침서가 없다고
        워크플로우 실행을 막지 않는다). system 필드 존재는 호출 전 `_supports_system`이 보장.
        """
        if self._skill_document_store is None:
            logger.debug("skill_id=%s 바인딩됐으나 store 미배선 — 주입 생략", skill_id)
            return node_input
        try:
            document = await self._skill_document_store.load(skill_id)
        except Exception:
            logger.warning("skill_id=%s 지침서 로드 실패 — 주입 생략(degrade)", skill_id, exc_info=True)
            return node_input
        if document is None:
            logger.warning("skill_id=%s 지침서 미존재 — 주입 생략", skill_id)
            return node_input
        merged = self._merge_system(document.instructions, getattr(node_input, "system", None))
        logger.info("skill_id=%s 지침서 주입 — system 프롬프트 %d자", skill_id, len(merged))
        return dataclasses.replace(node_input, system=merged)

    @staticmethod
    def _supports_system(node_instance: Any, config: NodeConfig) -> bool:
        """LLM 계열 노드인지 — `category=="ai"` AND input_schema에 'system' 필드 존재.

        category 단독은 system 미보유 노드를 잘못 잡고, system 필드 단독은 우연히 같은
        필드명을 쓰는 비-LLM 노드를 over-match하므로 둘 다 요구한다 (REQ-013 리뷰 LOW #5).
        """
        if getattr(config, "category", None) != "ai":
            return False
        schema = getattr(node_instance, "input_schema", None)
        if not dataclasses.is_dataclass(schema):
            return False
        return "system" in {f.name for f in dataclasses.fields(schema)}

    @staticmethod
    def _merge_system(instructions: str, existing: str | None) -> str:
        """지침서를 system에 병합 — 기존 system이 있으면 지침서를 앞에 두고 `---`로 구분."""
        instructions = (instructions or "").strip()
        if existing and existing.strip():
            return f"{instructions}\n\n---\n\n{existing.strip()}"
        return instructions

    @staticmethod
    def _build_input(node_instance: Any, node: NodeInstance, inputs: dict[str, Any]) -> Any:
        """노드 parameters + 런타임 inputs를 노드의 input_schema 데이터클래스로 변환."""
        merged = {**node.parameters, **inputs}
        field_names = {f.name for f in dataclasses.fields(node_instance.input_schema)}
        kwargs = {k: v for k, v in merged.items() if k in field_names}
        return node_instance.input_schema(**kwargs)

    @staticmethod
    def _to_dict(output: Any) -> dict[str, Any]:
        """노드 output 데이터클래스를 NodeExecutorPort 계약(dict)으로 변환."""
        if dataclasses.is_dataclass(output) and not isinstance(output, type):
            return dataclasses.asdict(output)
        if isinstance(output, dict):
            return output
        return {"result": output}
