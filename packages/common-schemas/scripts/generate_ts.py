"""
TypeScript codegen: Pydantic v2 models → TypeScript interfaces.

Usage:
    python scripts/generate_ts.py

Output:
    typescript/src/generated/index.ts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Union, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel

HEADER = '''\
// Auto-generated from Python common_schemas — DO NOT EDIT
// Regenerate: python scripts/generate_ts.py

'''

PYTHON_TO_TS: dict[Any, str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    UUID: "string",
}


def _resolve_type(annotation: Any) -> str:
    origin = get_origin(annotation)

    if annotation is Any:
        return "unknown"

    if annotation in PYTHON_TO_TS:
        return PYTHON_TO_TS[annotation]

    if origin is list:
        inner = get_args(annotation)[0] if get_args(annotation) else Any
        return f"Array<{_resolve_type(inner)}>"

    if origin is dict:
        args = get_args(annotation)
        key_t = _resolve_type(args[0]) if args else "string"
        val_t = _resolve_type(args[1]) if len(args) > 1 else "unknown"
        return f"Record<{key_t}, {val_t}>"

    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return f"{_resolve_type(args[0])} | null"
        return " | ".join(_resolve_type(a) for a in args)

    from enum import Enum as StdEnum

    if isinstance(annotation, type) and issubclass(annotation, StdEnum):
        values = [json.dumps(m.value) for m in annotation]
        return " | ".join(values)

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__

    if hasattr(annotation, "__args__"):
        args = get_args(annotation)
        if args and all(isinstance(a, str) for a in args):
            return " | ".join(json.dumps(a) for a in args)

    return "unknown"


def _model_to_interface(model: type[BaseModel]) -> str:
    lines = [f"export interface {model.__name__} {{"]
    for name, field_info in model.model_fields.items():
        annotation = field_info.annotation
        optional = not field_info.is_required()

        origin = get_origin(annotation)
        if origin is Union:
            args = get_args(annotation)
            non_none = [a for a in args if a is not type(None)]
            has_none = len(non_none) < len(args)
            if has_none and len(non_none) == 1:
                ts_type = _resolve_type(non_none[0]) + " | null"
            else:
                ts_type = _resolve_type(annotation)
        else:
            ts_type = _resolve_type(annotation)

        opt = "?" if optional else ""
        lines.append(f"  {name}{opt}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def _enum_to_ts(enum_cls: type) -> str:
    lines = [f"export enum {enum_cls.__name__} {{"]
    for member in enum_cls:
        lines.append(f"  {member.name} = {json.dumps(member.value)},")
    lines.append("}")
    return "\n".join(lines)


def generate() -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

    from common_schemas.enums import AgentMode, ErrorCode, ExecutionStatus, RiskLevel
    from common_schemas.agent import AgentState, DraftSpec, IntentResult, SlotFillingState, UnresolvedNode
    from common_schemas.document import (
        AnalysisResult, BBox, ContentBlock, DocumentBlock, FileMeta, ParserMeta, SheetMeta, SourceRef,
    )
    from common_schemas.handoff import EvaluationResult, HandoffPayload
    from common_schemas.security import PermissionSource, PlaintextCredential
    from common_schemas.transport import (
        AgentNodeFrame, DraftSpecDeltaFrame, ErrorFrame, RationaleDeltaFrame,
        ResultFrame, SessionFrame, SlotFillQuestionFrame, SSEFrame,
    )
    from common_schemas.validation import ValidationErrorItem, ValidationErrorResponse
    from common_schemas.workflow import Edge, NodeConfig, NodeInstance, Position, WorkflowSchema

    enums = [AgentMode, ExecutionStatus, RiskLevel, ErrorCode]
    models = [
        Position, Edge, NodeInstance, NodeConfig, WorkflowSchema,
        BBox, SheetMeta, ParserMeta, SourceRef, FileMeta, ContentBlock, DocumentBlock, AnalysisResult,
        UnresolvedNode, SlotFillingState, DraftSpec, IntentResult, AgentState,
        SSEFrame, SessionFrame, AgentNodeFrame, RationaleDeltaFrame,
        SlotFillQuestionFrame, DraftSpecDeltaFrame, ResultFrame, ErrorFrame,
        ValidationErrorItem, ValidationErrorResponse,
        PermissionSource, PlaintextCredential,
        HandoffPayload, EvaluationResult,
    ]

    parts = [HEADER]
    for e in enums:
        parts.append(_enum_to_ts(e))
        parts.append("")

    for m in models:
        parts.append(_model_to_interface(m))
        parts.append("")

    frame_types = [
        "SessionFrame", "AgentNodeFrame", "RationaleDeltaFrame",
        "SlotFillQuestionFrame", "DraftSpecDeltaFrame", "ResultFrame", "ErrorFrame",
    ]
    parts.append(f"export type AnySSEFrame = {' | '.join(frame_types)};")
    parts.append("")

    return "\n".join(parts)


def main() -> None:
    output_dir = Path(__file__).resolve().parent.parent / "typescript" / "src" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    content = generate()
    out_file = output_dir / "index.ts"
    out_file.write_text(content, encoding="utf-8")
    print(f"Generated: {out_file.name} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
