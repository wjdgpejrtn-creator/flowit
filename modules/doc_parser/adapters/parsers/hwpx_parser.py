"""
REQ-006 doc_parser — adapters/parsers/hwpx_parser.py

HwpxParser
ZIP + lxml 기반 HWPX 2.0 파서

페이지 산출 (v1.2):
    HWPX 에는 PDF 의 len(pdf) 같은 "확정 페이지 수" 필드가 없다.
    페이지 수는 한글이 저장 시 계산해 lineseg(줄 배치 캐시)에 박아둔 vertpos 로만 복원 가능하다.
    단, 표/컨트롤 셀 내부 lineseg 의 vertpos 는 '셀 상대' 값이라 페이지 신호를 오염시킨다.
    → 최상위 본문 단락(중첩되지 않은 hp:p)의 lineseg vertpos 만 사용한다.
    → 본문이 페이지 하단까지 내려갔다가(>= 0.5*페이지높이) 상단(< 0.25*페이지높이)으로
      되돌아오는 지점을 페이지 경계로 본다. (page-height-relative reset)
    이 매핑으로 page_count 와 각 블록의 page 번호를 함께 산출한다.

제한 사항 (MVP):
    - 복잡 표·서식 완전 복원 불가 / 이미지 내 텍스트 제외
    - 본문 텍스트는 section0 만 파싱 → block.page 는 section0 기준 (page_count 만 전 섹션)
    - 레이아웃 캐시가 없는 문서(한글 외 도구 생성)는 페이지 수를 정확히 알 수 없어 하한선 추정
    - 페이지 경계는 휴리스틱 → 한글 표시 페이지 수와 ±1 오차 가능 (검증: tests/test_hwpx_page_count.py 골든 케이스)
"""
from __future__ import annotations

import logging
import re
import zipfile
from uuid import uuid4

from lxml import etree

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
    SourceRef,
)

from doc_parser.domain.ports.parser_port import ParserPort

logger = logging.getLogger(__name__)

_CONTENT_CANDIDATES = ["Contents/section0.xml", "word/document.xml"]
_SECTION_RE = re.compile(r"Contents/section(\d+)\.xml$")

# 페이지 리셋 임계값: 새 줄의 vertpos 가 현재 페이지 최대 vertpos 의 이 비율 미만이면
# 페이지가 넘어가 본문이 상단으로 되돌아온 것으로 본다. (실측 5종 보정값)
_RESET_RATIO = 0.6

# 과소집계 트리거: 표 내부 lineseg 비중이 이 값 이상이면, 페이지를 걸치는 큰 표가
# 본문을 압도해 page_count 가 실제보다 낮게 집계됐을 위험으로 본다.
# (실측 5종 보정: 정확히 맞은 문서들 ≤ 0.76, 과소집계된 문서 0.90)
_UNDERCOUNT_TBL_FRAC = 0.85
_UNDERCOUNT_NOTE = (
    "페이지를 걸치는 큰 표가 본문 대부분을 차지해 page_count 가 실제보다 낮게 "
    "집계됐을 수 있습니다(데이터 유실 아님 — 표는 vision 이미지로 보존). "
    "coverage 분모가 보수적으로 계산됨."
)
_PAGE_BREAK_TRUE = {"1", "true", "True", "TRUE", "on"}
_PAGE_ATTR = "_dp_page"  # 최상위 단락에 임시로 기록하는 페이지 번호 속성


class HwpxParser(ParserPort):
    """HWPX 2.0 파서 구현체.

    지원 MIME 타입: application/hwp+zip

    Raises:
        RuntimeError: HWPX XML 파싱 실패 E0208 / 파일 손상·읽기 실패 E0202
    """

    MIME_TYPE = "application/hwp+zip"

    def parse(self, file_path: str, file_meta: FileMeta) -> DocumentBlock:
        xml_bytes = self._extract_xml(file_path)
        try:
            blocks = self._parse_xml(xml_bytes)
            page_count, undercount_risk = self._count_pages(file_path)

            update: dict = {"page_count": page_count}
            if undercount_risk:
                logger.warning(
                    "PAGE_COUNT_UNDERESTIMATE_RISK page_count=%d file=%s — %s",
                    page_count, file_path, _UNDERCOUNT_NOTE,
                )
                update["notes"] = _UNDERCOUNT_NOTE
            try:
                new_meta = file_meta.model_copy(update=update)
            except Exception:
                # FileMeta 에 notes 필드가 없으면 page_count 만 반영 (경고 로그는 이미 남음)
                new_meta = file_meta.model_copy(update={"page_count": page_count})

            return DocumentBlock(
                document_id=uuid4(),
                file_meta=new_meta,
                parser=ParserMeta(parser_name="HwpxParser", parser_version="1.3.0"),
                blocks=blocks,
            )
        except Exception as e:
            raise RuntimeError(f"E0208: HWPX XML 파싱 실패 — {e}") from e

    def supports(self, mime_type: str) -> bool:
        return mime_type == self.MIME_TYPE

    # ──────────────────────────────────────────
    # 레이아웃 분석 (페이지 수 + 단락별 페이지 매핑)
    # ──────────────────────────────────────────

    def _analyze_layout(self, root) -> tuple[int, bool]:
        """최상위 본문 단락 기준 페이지 분석.

        각 최상위 단락 노드에 페이지 번호를 임시 속성(_PAGE_ATTR)으로 기록한다.
        (lxml 은 같은 노드라도 순회마다 다른 프록시를 반환할 수 있어 id() 키가
        불안정하다 → 노드 속성에 저장해 별도 순회에서도 안전하게 읽는다.)

        Returns:
            (total_pages, had_layout_cache)
        """
        top_ps = self._top_level_paragraphs(root)

        seq: list[int] = []
        first_idx: list[int | None] = []
        for p in top_ps:
            vps = self._direct_vertpos(p)
            first_idx.append(len(seq) if vps else None)
            seq.extend(vps)

        had_cache = len(seq) > 0

        pages_at: list[int] = []
        pages = 1
        page_max: int | None = None
        for v in seq:
            if page_max is None:
                page_max = v
            elif v < page_max * _RESET_RATIO:
                pages += 1
                page_max = v
            else:
                page_max = max(page_max, v)
            pages_at.append(pages)

        total = pages_at[-1] if pages_at else 1

        last = 1
        for p, idx in zip(top_ps, first_idx):
            pg = pages_at[idx] if (idx is not None and idx < len(pages_at)) else last
            p.set(_PAGE_ATTR, str(pg))
            last = pg

        return total, had_cache

    def _count_pages(self, file_path: str) -> tuple[int, bool]:
        """문서 전체 실제 페이지 수 산출 (전 섹션 합산).

        신호: 레이아웃 캐시(vertpos reset) → max(명시적 pageBreak 하한선).
        캐시가 전혀 없으면 하한선 추정값 + 경고. 실패 시 1 폴백.
        """
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                section_names = sorted(
                    (n for n in zf.namelist() if _SECTION_RE.match(n)),
                    key=lambda n: int(_SECTION_RE.match(n).group(1)),
                )
                if not section_names:
                    return 1

                total = 0
                saw_cache = False
                top_ls = tbl_ls = 0
                for name in section_names:
                    pages, had_cache, t_top, t_tbl = self._count_section_pages(zf.read(name))
                    saw_cache = saw_cache or had_cache
                    total += pages
                    top_ls += t_top
                    tbl_ls += t_tbl

                if not saw_cache:
                    logger.warning(
                        "HWPX 레이아웃 캐시 없음 — page_count=%d 는 하한선 추정값 "
                        "(한글에서 저장된 문서가 아닐 수 있음): %s", total, file_path,
                    )

                total_ls = top_ls + tbl_ls
                undercount_risk = (
                    total_ls > 0 and (tbl_ls / total_ls) >= _UNDERCOUNT_TBL_FRAC
                )
                return max(total, 1), undercount_risk

        except zipfile.BadZipFile:
            logger.warning("page_count: 손상 ZIP — 1 폴백: %s", file_path)
            return 1, False
        except Exception:
            logger.exception("page_count 산출 실패 — 1 폴백: %s", file_path)
            return 1, False

    def _count_section_pages(self, xml_bytes: bytes) -> tuple[int, bool, int, int]:
        """Returns: (pages, had_layout_cache, top_lineseg_cnt, table_lineseg_cnt)"""
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError:
            return 1, False, 0, 0

        total, had_cache = self._analyze_layout(root)

        explicit_breaks = sum(
            1 for e in root.iter()
            if self._lname(e) == "p"
            and (self._attr_ci(e, "pageBreak") or "") in _PAGE_BREAK_TRUE
        )

        top_ls = tbl_ls = 0
        for ls in root.iter():
            if self._lname(ls) != "lineseg":
                continue
            if self._to_int(self._attr_ci(ls, "vertpos")) is None:
                continue
            if self._in_table(ls):
                tbl_ls += 1
            else:
                top_ls += 1

        return max(total, 1 + explicit_breaks), had_cache, top_ls, tbl_ls

    def _in_table(self, elem) -> bool:
        a = elem.getparent()
        while a is not None:
            if self._lname(a) in ("tbl", "table"):
                return True
            a = a.getparent()
        return False

    # ── 레이아웃 헬퍼 ──

    @staticmethod
    def _lname(elem) -> str:
        return etree.QName(elem.tag).localname.lower() if elem.tag is not None else ""

    def _top_level_paragraphs(self, root) -> list:
        """중첩되지 않은(표/컨트롤 내부가 아닌) hp:p 들을 문서 순서로 반환."""
        out = []
        for p in root.iter():
            if self._lname(p) != "p":
                continue
            anc = p.getparent()
            nested = False
            while anc is not None:
                if self._lname(anc) == "p":
                    nested = True
                    break
                anc = anc.getparent()
            if not nested:
                out.append(p)
        return out

    def _direct_vertpos(self, p) -> list[int]:
        """단락 p 의 '직속' linesegarray vertpos 목록 (중첩 p 의 것은 제외)."""
        out: list[int] = []
        for lsa in p.iter():
            if self._lname(lsa) != "linesegarray":
                continue
            anc = lsa.getparent()
            owner = None
            while anc is not None:
                if self._lname(anc) == "p":
                    owner = anc
                    break
                anc = anc.getparent()
            if owner is not p:
                continue
            for ls in lsa:
                if self._lname(ls) == "lineseg":
                    v = self._to_int(self._attr_ci(ls, "vertpos"))
                    if v is not None:
                        out.append(v)
        return out

    def _page_for(self, elem) -> int:
        """elem 이 속한 최상위 단락의 page 번호 (없으면 1)."""
        node = elem
        top_p = None
        while node is not None:
            if self._lname(node) == "p":
                top_p = node
            node = node.getparent()
        if top_p is None:
            return 1
        return int(top_p.get(_PAGE_ATTR, "1"))

    @staticmethod
    def _attr_ci(elem, name: str) -> str | None:
        nl = name.lower()
        for k, v in elem.attrib.items():
            local = etree.QName(k).localname if "}" in k else k
            if local.lower() == nl:
                return v
        return None

    @staticmethod
    def _to_int(raw: str | None) -> int | None:
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            try:
                return int(float(raw))
            except ValueError:
                return None

    # ──────────────────────────────────────────
    # 본문 추출
    # ──────────────────────────────────────────

    def _extract_xml(self, file_path: str) -> bytes:
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                names = zf.namelist()
                content_path = None
                for candidate in _CONTENT_CANDIDATES:
                    if candidate in names:
                        content_path = candidate
                        break
                if not content_path:
                    for name in names:
                        if re.match(r"Contents/section\d+\.xml", name):
                            content_path = name
                            break
                if not content_path:
                    raise RuntimeError(
                        f"E0208: HWPX XML 파싱 실패 — 본문 파일을 찾을 수 없음. "
                        f"포함된 파일: {names}"
                    )
                return zf.read(content_path)
        except zipfile.BadZipFile as e:
            raise RuntimeError(f"E0202: HWPX 파일 읽기 실패 — {e}") from e
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"E0202: HWPX 파일 읽기 실패 — {e}") from e

    def _parse_xml(self, xml_bytes: bytes) -> list[ContentBlock]:
        """lxml → ContentBlock 목록. block.page 는 레이아웃 매핑에서 부여."""
        blocks: list[ContentBlock] = []
        block_index = 0

        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            raise RuntimeError(f"E0208: HWPX XML 파싱 실패 — XML 형식 오류: {e}") from e

        self._analyze_layout(root)

        for elem in root.iter():
            tag = etree.QName(elem.tag).localname if elem.tag is not None else ""

            if tag == "p":
                text = self._extract_para_text(elem)
                if not text:
                    continue
                page_num = self._page_for(elem)
                blocks.append(ContentBlock(
                    block_id=uuid4(),
                    block_type=self._detect_block_type(text),
                    content=text,
                    page=page_num,
                    source_ref=SourceRef(page=page_num, block_index=block_index),
                ))
                block_index += 1

            elif tag in ("tbl", "table"):
                table_data = self._extract_table(elem)
                if not table_data:
                    continue
                page_num = self._page_for(elem)
                blocks.append(ContentBlock(
                    block_id=uuid4(),
                    block_type="table",
                    content=None,
                    page=page_num,
                    table=table_data,
                    source_ref=SourceRef(page=page_num, block_index=block_index),
                ))
                block_index += 1

        return blocks

    def _extract_para_text(self, para_elem) -> str:
        texts = []
        for elem in para_elem.iter():
            tag = etree.QName(elem.tag).localname if elem.tag else ""
            if tag in ("t", "run", "r") and elem.text:
                texts.append(elem.text)
        return " ".join(texts).strip()

    def _extract_table(self, tbl_elem) -> list[list[str]]:
        rows = []
        for elem in tbl_elem.iter():
            tag = etree.QName(elem.tag).localname if elem.tag else ""
            if tag in ("tr", "row"):
                cells = []
                for cell_elem in elem.iter():
                    cell_tag = etree.QName(cell_elem.tag).localname if cell_elem.tag else ""
                    if cell_tag in ("tc", "cell"):
                        cell_texts = []
                        for t_elem in cell_elem.iter():
                            t_tag = etree.QName(t_elem.tag).localname if t_elem.tag else ""
                            if t_tag in ("t", "run", "r") and t_elem.text:
                                cell_texts.append(t_elem.text)
                        cell_text = " ".join(cell_texts).strip()
                        if cell_text:
                            cells.append(cell_text)
                if cells:
                    rows.append(cells)
        return rows

    def _detect_block_type(self, text: str) -> str:
        text = text.strip()
        is_short = len(text) <= 50
        no_newline = "\n" not in text
        numbered = bool(re.match(
            r"^(\d+[\.\)]|제\s*\d+\s*[조항절장]|[가-힣]\.|[IVX]+\.)\s", text
        ))
        if is_short and no_newline and numbered:
            return "heading"
        if is_short and no_newline and text.endswith(("장", "절", "항", "조")):
            return "heading"
        return "text"
