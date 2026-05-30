from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from common_schemas import DraftSpec, Edge, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort

_logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a workflow drafter. Given a DraftSpec and candidate nodes,
output a JSON object matching this schema:
{
  "name": "<string>",
  "scope": "private",
  "is_draft": true,
  "nodes": [{"node_type": "<type>", "parameters": {"<param_key>": "<value>"}, "x": 0, "y": 0}],
  "connections": [{"from_node_type": "<type>", "to_node_type": "<type>", "from_handle": "output", "to_handle": "input"}]
}
Only use nodes from the provided candidate list.
Each node_type must appear at most once in the nodes list.
Connections define execution order: from_node_type runs before to_node_type.
Use "output" for from_handle and "input" for to_handle unless specific handles are needed.
Fill in `parameters` for each node using:
1. Values extracted from DraftSpec entities (e.g. schedule time, service names, channels).
2. The node's input_schema (a JSON Schema with `properties`, `required`, `default`) as a guide
   for which fields to fill. Fill every field listed in `required`; when the user did not specify
   a value, use the field's `default` if present.
3. Use an empty string "" only for optional fields the user did not specify that have no default.
"""


# LLM 응답 전용 — common_schemas.WorkflowSchema의 owner_user_id/workflow_id 제외 부분집합.
# WorkflowSchema 필드 추가 시 이 모델도 확인 필요 (silent drift 방지).
class _NodeDraft(BaseModel):
    node_type: str
    parameters: dict[str, Any] = {}
    x: float = 0.0
    y: float = 0.0


class _EdgeDraft(BaseModel):
    from_node_type: str
    to_node_type: str
    from_handle: str = "output"
    to_handle: str = "input"


class _DraftResponse(BaseModel):
    name: str = "Untitled Workflow"
    scope: str = "private"
    is_draft: bool = True
    nodes: list[_NodeDraft] = []
    connections: list[_EdgeDraft] = []


class DrafterService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def draft(self, spec: DraftSpec, candidates: list[NodeConfig], owner_user_id: UUID) -> WorkflowSchema:
        catalog = [
            {
                "node_type": n.node_type,
                "name": n.name,
                "description": n.description,
                "input_schema": n.input_schema,
            }
            for n in candidates
        ]
        prompt = (
            _SYSTEM_PROMPT
            + f"\nDraftSpec: {json.dumps({'intent': spec.natural_language_intent, 'entities': spec.discovered_entities}, ensure_ascii=False)}"
            + f"\nAvailable nodes: {json.dumps(catalog, ensure_ascii=False)}"
        )
        try:
            draft_resp = await self._llm.generate_structured(prompt, _DraftResponse)
        except Exception as e:
            raise ExecutionError(f"WorkflowSchema 파싱 실패: {e}", code="E_DRAFT_PARSE")
        return self._build(draft_resp, candidates, owner_user_id)

    def _build(self, draft: _DraftResponse, candidates: list[NodeConfig], owner_user_id: UUID) -> WorkflowSchema:
        try:
            node_map = {n.node_type: n for n in candidates}
            nodes: list[NodeInstance] = []
            instance_id_map: dict[str, UUID] = {}  # node_type → instance_id (1:1 보장)
            for raw in draft.nodes:
                nc = node_map.get(raw.node_type)
                if nc is None:
                    raise ExecutionError(
                        f"후보 목록에 없는 node_type: {raw.node_type}",
                        code="E_UNKNOWN_NODE_TYPE",
                    )
                if raw.node_type in instance_id_map:
                    raise ExecutionError(
                        f"node_type 중복 사용 불가: {raw.node_type}",
                        code="E_DUPLICATE_NODE_TYPE",
                    )
                instance_id = uuid4()
                instance_id_map[raw.node_type] = instance_id
                nodes.append(
                    NodeInstance(
                        instance_id=instance_id,
                        node_id=nc.node_id,
                        parameters=raw.parameters,
                        position=Position(x=raw.x, y=raw.y),
                    )
                )

            connections: list[Edge] = []
            for edge in draft.connections:
                from_id = instance_id_map.get(edge.from_node_type)
                to_id = instance_id_map.get(edge.to_node_type)
                if from_id is None or to_id is None:
                    _logger.warning(
                        "엣지 건너뜀 — 알 수 없는 node_type: %s → %s",
                        edge.from_node_type,
                        edge.to_node_type,
                    )
                    continue
                connections.append(
                    Edge(
                        from_instance_id=from_id,
                        to_instance_id=to_id,
                        from_handle=edge.from_handle,
                        to_handle=edge.to_handle,
                    )
                )

            return WorkflowSchema(
                workflow_id=uuid4(),
                name=draft.name,
                scope=draft.scope,
                is_draft=True,
                nodes=nodes,
                connections=connections,
                owner_user_id=owner_user_id,
            )
        except ExecutionError:
            raise
        except Exception as e:
            raise ExecutionError(f"WorkflowSchema 빌드 실패: {e}", code="E_DRAFT_PARSE")
