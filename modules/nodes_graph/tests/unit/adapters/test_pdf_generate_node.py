"""pdf_generate 노드 동작 회귀 테스트.

배경: fpdf2 코어 폰트(Helvetica)는 latin-1만 지원 + 생성자가 margin 인자를 받지 않아
PDF 노드가 staging에서 한 번도 정상 동작하지 못했다(생성자 TypeError + 한글
FPDFUnicodeEncodingException). 본 테스트는 다음 회귀를 고정한다.
  - margin 적용이 생성자가 아닌 set_margin 경로로 동작
  - 유니코드(한글) 텍스트 렌더링
  - 미지원 글리프(이모지)·과대 margin·잘못된 section 형식에서 크래시하지 않음
"""
from __future__ import annotations

import base64
from uuid import uuid4

import pytest
from common_schemas import NodeContext

from nodes_graph.adapters.catalog.external.pdf_generate import (
    PdfGenerateInput,
    PdfGenerateNode,
)
from nodes_graph.adapters.catalog.external.pdf_generate import (
    get_node_definition as pdf_generate_def,
)

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


def _assert_pdf(output) -> None:
    # pdf_bytes는 base64 인코딩 문자열(#535: node_results JSONB 직렬화 위해 str로 반환)
    assert isinstance(output.pdf_bytes, str)
    raw = base64.b64decode(output.pdf_bytes)
    assert raw.startswith(b"%PDF"), "유효한 PDF 헤더가 아님"
    assert output.page_count >= 1


@pytest.mark.asyncio
async def test_ascii_basic() -> None:
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(
            title="Weekly Summary",
            sections=[{"heading": "Top Mails", "body": "Body content."}],
        ),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_korean_text_renders() -> None:
    """한글 제목·본문이 예외 없이 PDF로 렌더링된다(핵심 회귀)."""
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(
            title="주간 메일 요약",
            sections=[
                {"heading": "핵심 메일", "body": "오늘 받은 메일 3건 요약입니다."},
                {"heading": "액션 아이템", "body": "내일까지 회신이 필요합니다."},
            ],
            font_size=12,
            margin=15,
        ),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_unsupported_glyph_does_not_crash() -> None:
    """이모지 등 폰트 미지원 글리프는 예외 대신 경고로 강등되어 크래시하지 않는다."""
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(
            title="완료 보고 ✅",
            sections=[{"heading": "결과 🚀", "body": "정상 처리됨 👍"}],
        ),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_oversized_margin_clamped() -> None:
    """페이지 폭 절반 이상 margin도 클램프되어 'Not enough horizontal space' 크래시가 없다."""
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(title="제목", sections=[{"heading": "H", "body": "본문"}], margin=200),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_extreme_font_size_clamped() -> None:
    node = PdfGenerateNode()
    for size in (0, -5, 500):
        out = await node.process(
            PdfGenerateInput(title="제목", sections=[{"heading": "H", "body": "본문"}], font_size=size),
            NODE_CTX,
        )
        _assert_pdf(out)


@pytest.mark.asyncio
async def test_string_typed_numeric_params_do_not_crash() -> None:
    """LLM이 font_size/margin을 문자열로 줘도(JSON 숫자→문자열 흔함) 크래시하지 않는다."""
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(
            title="제목",
            sections=[{"heading": "H", "body": "본문"}],
            font_size="14",  # type: ignore[arg-type]
            margin="20",  # type: ignore[arg-type]
        ),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_malformed_sections_do_not_crash() -> None:
    """업스트림이 dict가 아닌 section(문자열/None/기타)을 줘도 방어적으로 처리한다."""
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(
            title="혼합 섹션",
            sections=[{"heading": "H", "body": "정상"}, "원시 문자열", None, 12345],  # type: ignore[list-item]
        ),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_non_string_title_does_not_crash() -> None:
    """title이 str이 아니어도(업스트림이 dict/숫자 등으로 줘도) 크래시하지 않는다."""
    node = PdfGenerateNode()
    for bad_title in ({"x": 1}, 12345, ["a", "b"]):
        out = await node.process(
            PdfGenerateInput(title=bad_title, sections=[{"heading": "H", "body": "본문"}]),  # type: ignore[arg-type]
            NODE_CTX,
        )
        _assert_pdf(out)


@pytest.mark.asyncio
async def test_empty_sections() -> None:
    node = PdfGenerateNode()
    out = await node.process(PdfGenerateInput(title="제목만", sections=[]), NODE_CTX)
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_multipage_page_count() -> None:
    node = PdfGenerateNode()
    sections = [{"heading": f"섹션{i}", "body": "문장입니다. " * 30} for i in range(60)]
    out = await node.process(PdfGenerateInput(title="긴 문서", sections=sections), NODE_CTX)
    _assert_pdf(out)
    assert out.page_count > 1, "다중 페이지 분할이 page_count에 반영되어야 함"


def test_node_definition_metadata() -> None:
    defn = pdf_generate_def()
    assert defn.node_type == "pdf_generate"
    assert defn.category == "output"
    assert defn.required_connections == []


# ── PR-A: body 키 alias (content/text) — 빈 PDF 버그 방어 ──────────────────


@pytest.mark.asyncio
async def test_section_content_key_alias() -> None:
    """드래퍼가 body 대신 content 키로 본문을 줘도 렌더된다(빈 PDF 버그 방어)."""
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(title="리포트", sections=[{"content": "본문 내용입니다."}]),
        NODE_CTX,
    )
    _assert_pdf(out)
    raw = base64.b64decode(out.pdf_bytes)
    # 본문이 실제로 들어갔으면 PDF가 제목만 있을 때보다 충분히 큼
    assert len(raw) > 2000


@pytest.mark.asyncio
async def test_section_text_key_alias() -> None:
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(title="리포트", sections=[{"title": "요약", "text": "텍스트 본문."}]),
        NODE_CTX,
    )
    _assert_pdf(out)


# ── PR-B: 마크다운 렌더(제목/볼드/불릿/표/인용) — AI 마크다운 리터럴 방지 ──────


@pytest.mark.asyncio
async def test_markdown_heading_bold_bullet_render() -> None:
    node = PdfGenerateNode()
    md = "## 핵심 지표\n* **총 매출액:** 176,100원\n* 총 주문 건수: 11건\n> 인용 줄입니다."
    out = await node.process(
        PdfGenerateInput(title="매출 리포트", sections=[{"body": md}]),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_markdown_table_render() -> None:
    """| 표 | 문법 | 이 실제 표로 렌더되고 구분선(:---)은 스킵된다(크래시 없음)."""
    node = PdfGenerateNode()
    md = (
        "## 카테고리별\n"
        "| 카테고리 | 매출 | 등급 |\n"
        "| :--- | :--- | :--- |\n"
        "| VOD_Premium | 97,800원 | S |\n"
        "| PPV_Movie | 38,000원 | A |\n"
    )
    out = await node.process(
        PdfGenerateInput(title="표 리포트", sections=[{"body": md}]),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_malformed_table_does_not_crash() -> None:
    node = PdfGenerateNode()
    md = "| 깨진 | 표\n| 셀 수 | 불일치 | 추가 | 셀 |\n일반 문장"
    out = await node.process(
        PdfGenerateInput(title="엣지", sections=[{"body": md}]),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_long_token_narrow_width_does_not_crash() -> None:
    """좁은 가용폭 + 공백 없는 초장문 토큰(URL 등)에서도 노드가 죽지 않는다(크래시 불변식)."""
    node = PdfGenerateNode()
    body = "참고: " + "x" * 4000 + "\n## 제목\n정상 문단"
    out = await node.process(
        PdfGenerateInput(title="엣지", sections=[{"body": body}], margin=90),
        NODE_CTX,
    )
    _assert_pdf(out)


# ── 회사 템플릿(style) — 스킬이 강제하는 시각 양식 ──────────────────────────


@pytest.mark.asyncio
async def test_style_template_renders() -> None:
    """style(회사명/accent/푸터/크기) 지정 시 헤더밴드·accent·푸터 적용, 크래시 없음."""
    node = PdfGenerateNode()
    style = {
        "org_name": "FLOWIT TELECOM (주)",
        "accent_color": "#1F6F54",
        "footer": "대외비 · 경영기획팀",
        "title_size": 20,
        "heading_size": 13,
    }
    body = "## 지표\n* **총매출:** 100원\n| A | B |\n| :--- | :--- |\n| 1 | 2 |"
    out = await node.process(
        PdfGenerateInput(
            title="전일 매출 리포트",
            sections=[{"heading": "요약", "body": body}],
            style=style,
        ),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_style_bad_accent_color_falls_back() -> None:
    """accent_color 형식 오류여도 기본색으로 폴백하고 크래시하지 않는다."""
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(
            title="리포트",
            sections=[{"body": "본문"}],
            style={"org_name": "회사", "accent_color": "not-a-color"},
        ),
        NODE_CTX,
    )
    _assert_pdf(out)


@pytest.mark.asyncio
async def test_no_style_backward_compatible() -> None:
    """style 미지정 시 기존 평문 렌더(하위호환)."""
    node = PdfGenerateNode()
    out = await node.process(
        PdfGenerateInput(title="평문", sections=[{"body": "본문 내용"}]),
        NODE_CTX,
    )
    _assert_pdf(out)
