from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
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

# 유니코드(한글 포함) 지원 번들 폰트. fpdf2 코어 폰트(Helvetica 등)는 latin-1만 지원하여
# 한글/CJK 텍스트에서 FPDFUnicodeEncodingException으로 즉시 실패한다. NanumGothic(OFL)을
# 번들해 한글 출력을 지원하고, 미지원 글리프(이모지 등)는 예외 대신 경고로 강등시킨다.
_FONT_FAMILY = "NanumGothic"
_FONT_DIR = Path(__file__).parent / "assets" / "fonts"
_FONT_REGULAR = _FONT_DIR / "NanumGothic-Regular.ttf"
_FONT_BOLD = _FONT_DIR / "NanumGothic-Bold.ttf"

# A4 기본 폭 210mm. margin이 폭의 절반 이상이면 가용 폭이 0 이하가 되어
# fpdf2가 "Not enough horizontal space"로 크래시한다 → 최소 가용 폭 확보를 위해 상한.
_MAX_MARGIN_MM = 90
_MIN_FONT_SIZE = 6
_MAX_FONT_SIZE = 72


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

    @staticmethod
    def _register_fonts(pdf: FPDF) -> None:
        """유니코드 폰트(regular/bold)를 등록. bold 변형을 등록하지 않으면
        style="B" 요청 시 'Undefined font'로 크래시하므로 둘 다 등록한다."""
        pdf.add_font(_FONT_FAMILY, "", str(_FONT_REGULAR))
        pdf.add_font(_FONT_FAMILY, "B", str(_FONT_BOLD))

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        """업스트림(LLM 등)이 숫자를 문자열("12") 등으로 줘도 클램프 비교에서
        TypeError가 나지 않도록 int로 강제. 변환 불가 시 기본값."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_sections(sections: Any) -> list[tuple[str, str]]:
        """sections 원소가 dict가 아닌 경우(문자열/None/기타)에도 크래시하지 않도록 정규화.
        업스트림(LLM 등)이 형식을 어긋나게 줘도 노드가 죽지 않게 방어한다.

        body 키는 ``body`` 정규형 외에 LLM/드래퍼가 흔히 쓰는 ``content``·``text``도 허용한다
        (드래퍼가 `${...}` 참조를 `content` 키로 매핑해 본문이 통째로 누락되던 빈 PDF 버그 방어).
        heading도 ``heading``·``title`` 모두 허용.
        """
        normalized: list[tuple[str, str]] = []
        for item in sections or []:
            if isinstance(item, dict):
                heading = str(item.get("heading") or item.get("title") or "")
                body = str(item.get("body") or item.get("content") or item.get("text") or "")
            elif item is None:
                continue
            elif isinstance(item, str):
                heading, body = "", item
            else:
                heading, body = "", str(item)
            if heading or body:
                normalized.append((heading, body))
        return normalized

    _RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
    _RE_BULLET = re.compile(r"^\s*[\*\-]\s+(.*)$")
    _RE_TABLE_SEP = re.compile(r"^:?-{2,}:?$")
    _RE_BOLD_STRIP = re.compile(r"\*\*(.+?)\*\*")

    @classmethod
    def _render_markdown_body(cls, pdf: FPDF, text: str, font_size: int) -> None:
        """본문 markdown을 실제 서식으로 렌더 — 제목(#)·표(|)·불릿(*,-)·인라인 볼드(**).

        fpdf2 코어 기능만 사용: heading은 bold 큰 글씨, 표는 ``pdf.table()``, 인라인 볼드는
        ``multi_cell(markdown=True)``. 파싱 불가/예외 시 해당 줄을 평문으로 폴백(절대 크래시 금지).
        """
        lines = (text or "").split("\n")
        i = 0
        while i < len(lines):
            raw = lines[i].rstrip()
            line = raw.strip()
            if not line:
                pdf.ln(2)
                i += 1
                continue

            mh = cls._RE_HEADING.match(line)
            if mh:
                level = len(mh.group(1))
                pdf.set_font(_FONT_FAMILY, "B", size=font_size + max(1, 4 - level))
                pdf.multi_cell(0, 7, mh.group(2), markdown=True, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)
                i += 1
                continue

            # 표 블록: 연속된 '|' 줄 수집
            if line.startswith("|"):
                rows: list[list[str]] = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    i += 1
                    # 구분선(| :--- | :--- |) 스킵
                    if cells and all(c == "" or cls._RE_TABLE_SEP.match(c) for c in cells):
                        continue
                    rows.append([cls._RE_BOLD_STRIP.sub(r"\1", c) for c in cells])
                if rows:
                    try:
                        pdf.set_font(_FONT_FAMILY, "", size=max(_MIN_FONT_SIZE, font_size - 1))
                        ncol = max(len(r) for r in rows)
                        with pdf.table(borders_layout="SINGLE_TOP_LINE", first_row_as_headings=True) as table:
                            for r in rows:
                                row = table.row()
                                for ci in range(ncol):
                                    row.cell(r[ci] if ci < len(r) else "")
                        pdf.ln(2)
                    except Exception:
                        # 표 렌더 실패 시 평문 폴백
                        pdf.set_font(_FONT_FAMILY, "", size=font_size)
                        for r in rows:
                            pdf.multi_cell(0, 6, " | ".join(r), new_x="LMARGIN", new_y="NEXT")
                continue

            mb = cls._RE_BULLET.match(raw)
            if mb:
                pdf.set_font(_FONT_FAMILY, "", size=font_size)
                pdf.multi_cell(0, 6, "·  " + mb.group(1), markdown=True, new_x="LMARGIN", new_y="NEXT")
                i += 1
                continue

            # 인용(blockquote) — 선두 '>' 제거하고 평문 렌더(리터럴 '>' 노출 방지)
            mq = re.match(r"^>+\s?(.*)$", line)
            if mq:
                pdf.set_font(_FONT_FAMILY, "", size=font_size)
                pdf.multi_cell(0, 6, mq.group(1), markdown=True, new_x="LMARGIN", new_y="NEXT")
                i += 1
                continue

            pdf.set_font(_FONT_FAMILY, "", size=font_size)
            pdf.multi_cell(0, 6, line, markdown=True, new_x="LMARGIN", new_y="NEXT")
            i += 1

    async def process(self, input: PdfGenerateInput, context: NodeContext) -> PdfGenerateOutput:
        font_size = max(_MIN_FONT_SIZE, min(_MAX_FONT_SIZE, self._coerce_int(input.font_size, 12)))
        margin = max(0, min(_MAX_MARGIN_MM, self._coerce_int(input.margin, 10)))

        pdf = FPDF()
        self._register_fonts(pdf)
        pdf.set_margin(margin)
        pdf.add_page()

        # 제목 — 길어도 줄바꿈되도록 multi_cell 사용(cell은 가로 오버플로우)
        pdf.set_font(_FONT_FAMILY, "B", size=font_size + 4)
        pdf.multi_cell(0, 10, str(input.title or ""), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        for heading, body in self._normalize_sections(input.sections):
            if heading:
                pdf.set_font(_FONT_FAMILY, "B", size=font_size + 1)
                pdf.multi_cell(0, 8, heading, new_x="LMARGIN", new_y="NEXT")
            if body:
                # 본문 markdown을 실제 서식(제목/표/볼드/불릿)으로 렌더 — LLM 산출물의
                # 마크다운이 날것 텍스트로 박히던 문제 해소.
                self._render_markdown_body(pdf, body, font_size)
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
                "font_size": {
                    "type": "integer",
                    "default": 12,
                    "description": "본문 글자 크기(pt). 기본값 12 (6~72pt로 제한)",
                },
                "margin": {
                    "type": "integer",
                    "default": 10,
                    "description": "페이지 여백(mm). 기본값 10 (0~90mm로 제한)",
                },
            },
            "required": ["title", "sections"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "pdf_bytes": {
                    "type": "string",
                    "format": "binary",
                    "description": (
                        "생성된 PDF(base64 인코딩 문자열). 이메일 첨부 등 하류 노드가 "
                        "${...pdf_bytes} 참조로 받는다."
                    ),
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
