from __future__ import annotations

import base64
from dataclasses import dataclass
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from fpdf import FPDF

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

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
    # base64 인코딩된 PDF 바이트(ASCII 문자열). 노드 출력은 node_results(JSONB)에 json.dumps로
    # 저장되므로 raw bytes는 직렬화 불가 → base64 문자열로 낸다(output_schema도 string/binary).
    # 하류 노드(email_send attachments 등)가 ${...pdf_bytes} 참조로 받아 base64 디코드해 사용.
    pdf_bytes: str
    page_count: int


class PdfGenerateNode(BaseNode[PdfGenerateInput, PdfGenerateOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="PDF 생성",
        category="output",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = PdfGenerateInput
    output_schema = PdfGenerateOutput

    async def process(self, input: PdfGenerateInput, context: NodeContext) -> PdfGenerateOutput:
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
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        return PdfGenerateOutput(pdf_bytes=pdf_b64, page_count=pdf.page)


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="PDF 생성",
        category="output",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "PDF 문서 제목"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"heading": {"type": "string"}, "body": {"type": "string"}},
                    },
                    "description": "문서를 구성할 섹션 목록(각 섹션은 제목·본문 포함)",
                },
                "font_size": {"type": "integer", "default": 12, "description": "본문 글자 크기(pt). 기본값 12"},
                "margin": {"type": "integer", "default": 10, "description": "페이지 여백(mm). 기본값 10"},
            },
            "required": ["title", "sections"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "pdf_bytes": {
                    "type": "string",
                    "format": "binary",
                    "description": "생성된 PDF(base64 인코딩 문자열). 이메일 첨부 등 하류 노드가 ${...pdf_bytes} 참조로 받는다.",
                },
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
