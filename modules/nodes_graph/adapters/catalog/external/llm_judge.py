from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError, ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "llm_judge"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT_SECONDS = 120  # LLM 추론은 느림 — 넉넉히
_DEFAULT_MODEL = "claude-haiku-4-5"  # 채점은 가볍고 빠른 모델 기본값


@dataclass
class LlmJudgeInput:
    content: str                       # 평가 대상 텍스트(예: 직전 generator 노드의 산출물)
    criteria: str                      # 평가 기준/루브릭
    model: str = _DEFAULT_MODEL
    min_score: int = 0                 # 점수 하한(포함)
    max_score: int = 10                # 점수 상한(포함)
    max_tokens: int = 512


@dataclass
class LlmJudgeOutput:
    score: float                       # 핵심 출력 — if_condition gte 등이 직접 비교
    reason: str                        # 채점 근거
    model: str
    usage: dict[str, int]              # {"input_tokens": .., "output_tokens": ..}


def _extract_json_object(text: str) -> dict[str, Any]:
    """LLM 응답 텍스트에서 첫 JSON 오브젝트를 추출. 코드펜스/머리말이 섞여도 견딘다."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ExecutionError(f"llm_judge: 응답에서 JSON 점수를 찾지 못함: {text[:200]}")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ExecutionError(f"llm_judge: JSON 파싱 실패: {text[:200]}") from exc
    if not isinstance(parsed, dict):
        raise ExecutionError(f"llm_judge: JSON 오브젝트가 아님: {text[:200]}")
    return parsed


class LlmJudgeNode(BaseNode[LlmJudgeInput, LlmJudgeOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="LLM 채점기",
        category="ai",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = LlmJudgeInput
    output_schema = LlmJudgeOutput

    async def process(self, input: LlmJudgeInput, context: NodeContext) -> LlmJudgeOutput:
        # connection_token = Anthropic API key (x-api-key 헤더). anthropic_chat 동일 자격증명.
        if not context.connection_token:
            raise ValidationError("llm_judge는 credential(Anthropic API key)이 필요하다")

        system = (
            "당신은 엄정한 평가자다. 주어진 [평가 대상]을 [평가 기준]에 따라 채점한다. "
            f"점수는 {input.min_score} 이상 {input.max_score} 이하의 정수다. "
            '반드시 다음 JSON 형식으로만 응답한다(다른 텍스트·코드펜스 금지): '
            '{"score": <정수>, "reason": "<채점 근거 한두 문장>"}'
        )
        user = f"[평가 기준]\n{input.criteria}\n\n[평가 대상]\n{input.content}"

        body: dict[str, Any] = {
            "model": input.model,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "max_tokens": input.max_tokens,
            "temperature": 0.0,  # 채점은 결정적이어야 — 온도 0
        }
        headers = {
            "x-api-key": context.connection_token,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_ANTHROPIC_API_URL, json=body, headers=headers)

        if response.status_code >= 400:
            raise ExecutionError(
                f"Anthropic API 오류 {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        parsed = _extract_json_object(text)
        if "score" not in parsed:
            raise ExecutionError(f"llm_judge: 응답에 score 필드 없음: {text[:200]}")
        try:
            raw_score = float(parsed["score"])
        except (TypeError, ValueError) as exc:
            raise ExecutionError(f"llm_judge: score가 숫자가 아님: {parsed.get('score')!r}") from exc
        # 모델이 범위를 벗어난 점수를 줄 수 있으므로 [min, max]로 클램프 — 결정적 게이트 안정성
        score = max(float(input.min_score), min(float(input.max_score), raw_score))
        return LlmJudgeOutput(
            score=score,
            reason=str(parsed.get("reason", "")),
            model=data.get("model", input.model),
            usage=data.get("usage", {}),
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="LLM 채점기",
        category="ai",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "평가 대상 텍스트"},
                "criteria": {"type": "string", "description": "평가 기준/루브릭"},
                "model": {"type": "string", "default": _DEFAULT_MODEL},
                "min_score": {"type": "integer", "default": 0},
                "max_score": {"type": "integer", "default": 10},
                "max_tokens": {"type": "integer", "default": 512},
            },
            "required": ["content", "criteria"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "score": {"type": "number", "description": "채점 점수 (if_condition gte 등이 비교)"},
                "reason": {"type": "string"},
                "model": {"type": "string"},
                "usage": {"type": "object"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["anthropic"],
        description=(
            "콘텐츠를 평가 기준에 따라 채점해 score(숫자)와 근거를 반환. "
            "품질 루프(generator→llm_judge→if_condition gte)에서 게이트 점수 산출. "
            "Anthropic API key 자격증명 필요"
        ),
        is_mvp=True,
        service_type="anthropic",
    )
