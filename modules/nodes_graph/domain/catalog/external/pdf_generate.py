from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel
from fpdf import FPDF

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "pdf_generate"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class PdfGenerateInput:
    title: str
    sections: list[dict[str, str]]  # [{"heading": "...", "body": "..."}, ...]
    font_size: int = 12
    margin: int = 10


@dataclass
class PdfGenerateOutput:
    pdf_bytes: bytes
    page_count: int


class PdfGenerateNode(BaseNode[PdfGenerateInput, PdfGenerateOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="PDF 생성",
        category="문서 생성",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = PdfGenerateInput
    output_schema = PdfGenerateOutput

    async def process(self, input: PdfGenerateInput) -> PdfGenerateOutput:
        pdf = FPDF(margin=input.margin)
        pdf.add_page()
        pdf.set_font("Helvetica", "B", size=input.font_size + 4)
        pdf.cell(0, 10, input.title, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        for section in input.sections:
            heading = section.get("heading", "")
            body = section.get("body", "")
            if heading:
                pdf.set_font("Helvetica", "B", size=input.font_size + 1)
                pdf.cell(0, 8, heading, new_x="LMARGIN", new_y="NEXT")
            if body:
                pdf.set_font("Helvetica", size=input.font_size)
                pdf.multi_cell(0, 6, body)
            pdf.ln(2)

        pdf_bytes = bytes(pdf.output())
        return PdfGenerateOutput(pdf_bytes=pdf_bytes, page_count=pdf.page)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="PDF 생성",
        category="문서 생성",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "body": {"type": "string"},
                        },
                    },
                },
                "font_size": {"type": "integer", "default": 12},
                "margin": {"type": "integer", "default": 10},
            },
            "required": ["title", "sections"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "pdf_bytes": {"type": "string", "format": "binary"},
                "page_count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="제목과 섹션 데이터로 PDF 파일 생성 (fpdf2 사용)",
        is_mvp=True,
        service_type=None,
    )
