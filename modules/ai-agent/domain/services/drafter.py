from __future__ import annotations

import json
from uuid import uuid4

from common_schemas import DraftSpec, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort

_SYSTEM_PROMPT = """You are a workflow drafter. Given a DraftSpec and candidate nodes,
output a JSON object matching WorkflowSchema:
{
  "name": "<string>",
  "scope": "private",
  "is_draft": true,
  "nodes": [{"node_type": "<type>", "parameters": {}, "x": 0, "y": 0}],
  "connections": []
}
Only use nodes from the provided candidate list.
"""


class DrafterService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def draft(self, spec: DraftSpec, candidates: list[NodeConfig]) -> WorkflowSchema:
        catalog = [
            {"node_type": n.node_type, "name": n.name, "description": n.description}
            for n in candidates
        ]
        prompt = (
            _SYSTEM_PROMPT
            + f"\nDraftSpec: {json.dumps({'intent': spec.natural_language_intent, 'entities': spec.discovered_entities}, ensure_ascii=False)}"
            + f"\nAvailable nodes: {json.dumps(catalog, ensure_ascii=False)}"
        )
        response = await self._llm.generate(prompt)
        return self._parse(response, candidates)

    def _parse(self, response: str, candidates: list[NodeConfig]) -> WorkflowSchema:
        try:
            data = json.loads(response)
            node_map = {n.node_type: n for n in candidates}
            nodes = []
            for raw in data.get("nodes", []):
                nc = node_map.get(raw.get("node_type"))
                if nc is None:
                    raise ExecutionError(
                        f"후보 목록에 없는 node_type: {raw.get('node_type')}",
                        code="E_UNKNOWN_NODE_TYPE",
                    )
                nodes.append(
                    NodeInstance(
                        instance_id=uuid4(),
                        node_id=nc.node_id,
                        parameters=raw.get("parameters", {}),
                        position=Position(x=raw.get("x", 0.0), y=raw.get("y", 0.0)),
                    )
                )
            return WorkflowSchema(
                workflow_id=uuid4(),
                name=data.get("name", "Untitled Workflow"),
                scope=data.get("scope", "private"),
                is_draft=True,
                nodes=nodes,
                connections=[],
            )
        except ExecutionError:
            raise
        except Exception as e:
            raise ExecutionError(f"WorkflowSchema 파싱 실패: {e}", code="E_DRAFT_PARSE")
