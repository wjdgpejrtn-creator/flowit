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
        """미바인딩·stale provider를 현재 active connection으로 동기화한 새 WorkflowSchema 반환.

        provider당 active connection은 ``get_active_for_user``가 **1개**만 반환한다
        (oauth_connections active partial unique index). 따라서 노드에 바인딩된 credential_id가
        그 active id와 다르면 **stale**(과거 연결 해제로 죽은 id)이라 교정 대상이고, 같으면 보존한다
        — 즉 "사용자 선택 보존"과 "stale 재바인딩"이 충돌하지 않는다(선택지가 단일 active 하나뿐).
        active connection이 없으면(미연결) 기존 바인딩을 보존한다(해소 불가 — 실행 시 정확히 실패).

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
            current = node.resolve_credentials(required)  # 현재 바인딩(credential_ids + legacy)
            new_binding = dict(node.credential_ids)
            for service in required:
                try:
                    active_cid = await self._resolver.resolve(user_id, service)
                except Exception as exc:  # connection 조회 실패는 비치명적 — 바인딩만 생략
                    _logger.warning("connection 자동 바인딩 조회 실패 (%s): %s", service, exc)
                    active_cid = None
                if active_cid is None:
                    continue  # 미연결 — 해소 불가, 기존 바인딩 보존
                if current.get(service) != active_cid:
                    # 미바인딩(키 없음) 또는 stale(active와 불일치) → 현재 active connection으로 교정
                    new_binding[service] = active_cid
            if new_binding != node.credential_ids:
                nodes[i] = node.model_copy(update={"credential_ids": new_binding})
                changed = True
        if not changed:
            return workflow
        return workflow.model_copy(update={"nodes": nodes})
