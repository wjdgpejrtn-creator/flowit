from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "number_calc"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class NumberCalcInput:
    operation: str  # add | sub | mul | div | mod | pow | abs | round | min | max | sum | ceil | floor | sqrt
    operands: list[float]
    ndigits: int = 0  # round 시 소수점 자릿수


@dataclass
class NumberCalcOutput:
    result: float


class NumberCalcNode(BaseNode[NumberCalcInput, NumberCalcOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="수식 계산",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = NumberCalcInput
    output_schema = NumberCalcOutput

    async def process(self, input: NumberCalcInput, context: NodeContext) -> NumberCalcOutput:
        ops = input.operands
        match input.operation:
            case "add" | "sum":
                result = sum(ops)
            case "sub":
                result = ops[0] - ops[1]
            case "mul":
                result = ops[0] * ops[1]
            case "div":
                result = ops[0] / ops[1]
            case "mod":
                result = ops[0] % ops[1]
            case "pow":
                result = ops[0] ** ops[1]
            case "abs":
                result = abs(ops[0])
            case "round":
                result = round(ops[0], input.ndigits)
            case "min":
                result = min(ops)
            case "max":
                result = max(ops)
            case "ceil":
                result = float(math.ceil(ops[0]))
            case "floor":
                result = float(math.floor(ops[0]))
            case "sqrt":
                result = math.sqrt(ops[0])
            case _:
                result = sum(ops)
        return NumberCalcOutput(result=result)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="수식 계산",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "add", "sub", "mul", "div", "mod", "pow",
                        "abs", "round", "min", "max", "sum", "ceil", "floor", "sqrt",
                    ],
                },
                "operands": {"type": "array", "items": {"type": "number"}},
                "ndigits": {"type": "integer", "default": 0},
            },
            "required": ["operation", "operands"],
        },
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "number"}},
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="사칙연산, 반올림, 집계(min/max/sum) 등 수치 계산",
        is_mvp=True,
        service_type=None,
    )
