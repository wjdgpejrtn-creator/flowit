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
    # 회사 문서 템플릿(선택) — 스킬이 강제하는 시각 양식. 미지정 시 기존 평문 렌더(하위호환).
    # 키: org_name(헤더 밴드 회사명) / accent_color(#hex, 헤더밴드·제목·섹션) /
    #     footer(푸터 문구) / title_size / heading_size / body_size.
    style: dict[str, Any] | None = None


_DEFAULT_ACCENT = (43, 92, 138)  # #2B5C8A


def _hex_to_rgb(value: Any, default: tuple[int, int, int] = _DEFAULT_ACCENT) -> tuple[int, int, int]:
    """'#RRGGBB' → (r,g,b). 형식 오류 시 default(노드 크래시 방지)."""
    try:
        s = str(value).lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (TypeError, ValueError, IndexError):
        return default


@dataclass
class PdfGenerateOutput:
    # base64 인코딩된 PDF 바이트(ASCII 문자열). 노드 출력은 node_results(JSONB)에 json.dumps로
    # 저장되므로 raw bytes는 직렬화 불가 → base64 문자열로 낸다(output_schema도 string/binary).
    # 하류 노드(email_send attachments 등)가 ${...pdf_bytes} 참조로 받아 base64 디코드해 사용.
    pdf_bytes: str
    page_count: int


class _ReportPDF(FPDF):
    """회사 템플릿용 FPDF 서브클래스 — accent 헤더 밴드(회사명) + 푸터(문구·페이지).

    header()/footer()는 fpdf2가 add_page·페이지 분기마다 자동 호출 → 모든 페이지에 일관 적용.
    style에 org_name/footer가 없으면 각각 그리지 않아 평문 모드와 호환.
    """

    def __init__(self, *args: Any, style: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._style = style or {}
        self._accent = _hex_to_rgb(self._style.get("accent_color"))

    def header(self) -> None:
        org = self._style.get("org_name")
        if not org:
            return
        self.set_fill_color(*self._accent)
        self.set_text_color(255, 255, 255)
        self.set_font(_FONT_FAMILY, "B", size=12)
        self.set_x(0)
        self.cell(0, 13, "   " + str(org), fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(5)

    def footer(self) -> None:
        ft = self._style.get("footer")
        if not ft:
            return
        self.set_y(-13)
        self.set_font(_FONT_FAMILY, "", size=8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"{ft}    |    p.{self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)


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
    def _render_markdown_body(
        cls, pdf: FPDF, text: str, font_size: int, accent: tuple[int, int, int] | None = None
    ) -> None:
        """본문 markdown을 실제 서식으로 렌더 — 제목(#)·표(|)·불릿(*,-)·인라인 볼드(**).

        fpdf2 코어 기능만 사용: heading은 bold 큰 글씨, 표는 ``pdf.table()``, 인라인 볼드는
        ``multi_cell(markdown=True)``. 파싱 불가/예외 시 해당 줄을 평문으로 폴백(절대 크래시 금지).
        accent 지정 시 markdown 제목(#)을 그 색으로 강조(회사 템플릿).
        """
        lines = (text or "").split("\n")
        i = 0
        while i < len(lines):
            # 줄 단위 렌더를 전부 try/except로 감싼다 — 좁은 가용폭에서 공백 없는 초장문
            # 토큰(URL 등)이 multi_cell "Not enough horizontal space"로 raise해도 그 줄만
            # 건너뛰고 노드 전체는 죽지 않게 한다(표 경로와 크래시 불변식 동등). i는 항상 전진.
            try:
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
                    if accent:
                        pdf.set_text_color(*accent)
                    pdf.multi_cell(0, 7, mh.group(2), markdown=True, new_x="LMARGIN", new_y="NEXT")
                    if accent:
                        pdf.set_text_color(0, 0, 0)
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
                            with pdf.table(
                                borders_layout="SINGLE_TOP_LINE", first_row_as_headings=True
                            ) as table:
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
            except Exception:
                # 어떤 줄이든 렌더 실패 시 그 줄만 스킵(노드 크래시 금지). i 전진 보장(무한루프 방지).
                i += 1
                continue

    async def process(self, input: PdfGenerateInput, context: NodeContext) -> PdfGenerateOutput:
        font_size = max(_MIN_FONT_SIZE, min(_MAX_FONT_SIZE, self._coerce_int(input.font_size, 12)))
        margin = max(0, min(_MAX_MARGIN_MM, self._coerce_int(input.margin, 10)))
        style = input.style if isinstance(input.style, dict) else None
        accent = _hex_to_rgb(style.get("accent_color")) if style else None
        title_size = self._coerce_int(style.get("title_size"), font_size + 6) if style else font_size + 4
        heading_size = self._coerce_int(style.get("heading_size"), font_size + 2) if style else font_size + 1

        # style 지정 시 헤더 밴드·푸터를 그리는 서브클래스 사용(미지정=기존 평문 FPDF, 하위호환).
        pdf: FPDF = _ReportPDF(style=style) if style else FPDF()
        self._register_fonts(pdf)
        pdf.set_margin(margin)
        pdf.add_page()

        # 제목 — 길어도 줄바꿈되도록 multi_cell 사용(cell은 가로 오버플로우)
        pdf.set_font(_FONT_FAMILY, "B", size=title_size)
        if accent:
            pdf.set_text_color(*accent)
        pdf.multi_cell(0, 10, str(input.title or ""), new_x="LMARGIN", new_y="NEXT")
        if accent:
            # 제목 하단 accent 구분선
            y = pdf.get_y() + 1
            pdf.set_draw_color(*accent)
            pdf.set_line_width(0.6)
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

        for heading, body in self._normalize_sections(input.sections):
            if heading:
                pdf.set_font(_FONT_FAMILY, "B", size=heading_size)
                if accent:
                    pdf.set_text_color(*accent)
                pdf.multi_cell(0, 8, heading, new_x="LMARGIN", new_y="NEXT")
                if accent:
                    pdf.set_text_color(0, 0, 0)
            if body:
                # 본문 markdown을 실제 서식(제목/표/볼드/불릿)으로 렌더 — LLM 산출물의
                # 마크다운이 날것 텍스트로 박히던 문제 해소.
                self._render_markdown_body(pdf, body, font_size, accent)
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
