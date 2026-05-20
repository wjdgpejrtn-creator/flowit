from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from common_schemas import DraftSpec, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort

_SYSTEM_PROMPT = """You are a workflow drafter. Given a DraftSpec and candidate nodes,
output a JSON object matching this schema:
{
  "name": "<string>",
  "scope": "private",
  "is_draft": true,
  "nodes": [{"node_type": "<type>", "parameters": {}, "x": 0, "y": 0}],
  "connections": []
}
Only use nodes from the provided candidate list.
"""


class _NodeDraft(BaseModel):
    node_type: str
    parameters: dict[str, Any] = {}
    x: float = 0.0
    y: float = 0.0


class _DraftResponse(BaseModel):
    name: str = "Untitled Workflow"
    scope: str = "private"
    is_draft: bool = True
    nodes: list[_NodeDraft] = []
    connections: list[Any] = []


class DrafterService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def draft(self, spec: DraftSpec, candidates: list[NodeConfig], owner_user_id: UUID) -> WorkflowSchema:
        catalog = [
            {"node_type": n.node_type, "name": n.name, "description": n.description}
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
            nodes = []
            for raw in draft.nodes:
                nc = node_map.get(raw.node_type)
                if nc is None:
                    raise ExecutionError(
                        f"후보 목록에 없는 node_type: {raw.node_type}",
                        code="E_UNKNOWN_NODE_TYPE",
                    )
                nodes.append(
                    NodeInstance(
                        instance_id=uuid4(),
                        node_id=nc.node_id,
                        parameters=raw.parameters,
                        position=Position(x=raw.x, y=raw.y),
                    )
                )
            return WorkflowSchema(
                workflow_id=uuid4(),
                name=draft.name,
                scope=draft.scope,
                is_draft=True,
                nodes=nodes,
                connections=[],
                owner_user_id=owner_user_id,
            )
        except ExecutionError:
            raise
        except Exception as e:
            raise ExecutionError(f"WorkflowSchema 빌드 실패: {e}", code="E_DRAFT_PARSE")
