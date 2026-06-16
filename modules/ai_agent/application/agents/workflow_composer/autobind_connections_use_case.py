"""AutobindConnectionsUseCase — 노드의 required_connections를 사용자 보유 connection으로 선바인딩.

Composer는 draft 생성 직후 `_autobind_connections`(candidates 기반)로 이미 선바인딩하지만,
**편집 페이지에서 추가/변경한 노드**는 그 경로를 타지 않아 `credential_ids`가 비어 있다.
그 노드를 저장/검증하면 `GraphValidator._check_required_connections`가 E_MISSING_CONNECTION을
낸다. 이 UseCase는 compose 외 경로(워크플로우 save·validate)에서 동일한 선바인딩을 수행한다.

candidates(NodeConfig 목록)가 없는 경로용이라, 각 노드의 required_connections를
`NodeDefinitionRepository.get_by_id`로 직접 조회한다(GraphValidator와 동일 소스).
이미 해소된 provider(사용자 명시 선택 / refine / legacy `credential_id`)는 보존한다.
"""
from __future__ import annotations

import logging
from uuid import UUID

from common_schemas import WorkflowSchema
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ....domain.ports.connection_resolver import ConnectionResolver

_logger = logging.getLogger(__name__)


class AutobindConnectionsUseCase:
    """워크플로우 노드의 미바인딩 required_connections를 사용자 active connection으로 채운다.

    바인딩은 ``credential_ids[provider] = credential_id`` 참조만 채우며, 실제 토큰 복호화·
    만료 시 refresh는 실행 시점 ``CredentialInjectionService``가 담당한다(REQ-012). 따라서
    토큰이 만료돼도 credential_id는 안정적이라 이 바인딩은 1회로 충분하다.
    """

    def __init__(
        self,
        resolver: ConnectionResolver,
        node_def_repo: NodeDefinitionRepository,
    ) -> None:
        self._resolver = resolver
        self._node_def_repo = node_def_repo

    async def execute(self, workflow: WorkflowSchema, user_id: UUID) -> WorkflowSchema:
        """미바인딩 provider를 채운 새 WorkflowSchema 반환. 변경 없으면 원본 그대로.

        조회 실패(resolver/repo 예외)는 비치명적 — 해당 provider 바인딩만 생략하고 진행한다.
        """
        nodes = list(workflow.nodes)
        changed = False
        for i, node in enumerate(nodes):
            try:
                definition = await self._node_def_repo.get_by_id(node.node_id)
            except Exception as exc:  # 정의 조회 실패는 비치명적 — 이 노드 선바인딩만 생략
                _logger.warning("노드 정의 조회 실패 (node_id=%s): %s", node.node_id, exc)
                continue
            if definition is None:
                continue
            required = definition.required_connections
            if not required:
                continue
            already = set(node.resolve_credentials(required).keys())
            new_binding = dict(node.credential_ids)
            for service in required:
                if service in already:
                    continue  # 이미 바인딩됨(사용자 선택/refine/legacy) — 보존
                try:
                    cid = await self._resolver.resolve(user_id, service)
                except Exception as exc:  # connection 조회 실패는 비치명적 — 바인딩만 생략
                    _logger.warning("connection 자동 바인딩 조회 실패 (%s): %s", service, exc)
                    cid = None
                if cid is not None:
                    new_binding[service] = cid
            if new_binding != node.credential_ids:
                nodes[i] = node.model_copy(update={"credential_ids": new_binding})
                changed = True
        if not changed:
            return workflow
        return workflow.model_copy(update={"nodes": nodes})
