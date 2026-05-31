"""
REQ-006 doc_parser — HWPX page_count 휴리스틱 회귀 테스트.

PR #247(+314) 의 page_count 산출 로직(vertpos/lineseg 페이지 경계 검출 +
다중 섹션 합산 + 표 과소집계 경고)에 대한 회귀 가드.

구성:
    1) 골든 케이스 — 한글에서 실제 페이지 수를 확인한 실파일 5종(tests/fixtures/).
       파서 산출값과 트리거(PAGE_COUNT_UNDERESTIMATE_RISK) 발생 여부를 고정.
    2) 합성 케이스 — 인메모리로 만든 HWPX 로 경계/멀티섹션/캐시부재/누적형/손상ZIP
       엣지를 픽스처 없이 검증.

주의:
    - 골든값은 "한글 표시 페이지 정답"이 아니라 "현 파서의 알려진 동작"을 고정한다.
      table_sample 은 정답 6 이지만, 다중 페이지 표 한계로 4 가 정상 동작이다
      (데이터 유실 없음 → 조장 승인). 표 보정이 들어가면 이 단언을 6 으로 올린다.
"""
from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pytest

from common_schemas.document import FileMeta
from doc_parser.adapters.parsers.hwpx_parser import HwpxParser

FIXTURES = Path(__file__).parent / "fixtures"
RISK_MARKER = "PAGE_COUNT_UNDERESTIMATE_RISK"


def _meta() -> FileMeta:
    return FileMeta(
        file_name="sample.hwpx",
        file_type="hwpx",
        mime_type="application/hwp+zip",
        file_size=1,
    )


# ──────────────────────────────────────────
# 1) 골든 케이스 — 실파일 (tests/fixtures/)
# ──────────────────────────────────────────
# (fixture 파일명, 기대 page_count, 과소집계 경고 기대, 원본 출처/한글 실측)
GOLDEN = [
    ("sample1.hwpx", 2, False, "공채시험 보도자료 — 한글 실측 2p"),
    ("sample2.hwpx", 3, False, "인재개발 보도자료 — 한글 실측 3p"),
    ("sample3.hwpx", 4, False, "적극행정 보도자료 — 한글 실측 4p"),
    ("text_sample.hwpx", 2, False, "텍스트 샘플 — 한글 실측 2p"),
    # 한글 실측 6p 이나 다중 페이지 표 한계로 4 가 정상(데이터 유실 없음 → 조장 OK).
    # 표 보정 도입 시 4 → 6 으로 상향.
    ("table_sample.hwpx", 4, True, "표 위주 샘플 — 실측 6p, 표 과소집계로 4 + 경고"),
]


@pytest.mark.parametrize("fname,expected,expect_warn,origin", GOLDEN)
def test_golden_page_count(fname, expected, expect_warn, origin, caplog):
    path = FIXTURES / fname
    if not path.exists():
        pytest.skip(f"픽스처 없음: {path} ({origin})")

    parser = HwpxParser()
    with caplog.at_level(logging.WARNING):
        doc = parser.parse(str(path), _meta())

    got = doc.file_meta.page_count
    assert got == expected, (
        f"{fname}: page_count={got}, 기대={expected} ({origin}). "
        f"sample1/2/3 ↔ 원본 매핑이 어긋났을 수 있음."
    )

    warned = any(RISK_MARKER in r.getMessage() for r in caplog.records)
    assert warned is expect_warn, (
        f"{fname}: 과소집계 경고={warned}, 기대={expect_warn} ({origin})"
    )


# ──────────────────────────────────────────
# 2) 합성 케이스 — 인메모리 HWPX
# ──────────────────────────────────────────
_NS = 'xmlns:hp="http://www.owpml.org/owpml/2021/paragraph"'


def _p(vertpos=None, page_break=False) -> str:
    pb = ' pageBreak="1"' if page_break else ' pageBreak="0"'
    segs = ""
    if vertpos is not None:
        segs = "<hp:linesegarray>" + "".join(
            f'<hp:lineseg textpos="0" vertpos="{v}" vertsize="1000" flags="393216"/>'
            for v in vertpos
        ) + "</hp:linesegarray>"
    return f'<hp:p{pb}><hp:run charPrIDRef="0"><hp:t>x</hp:t></hp:run>{segs}</hp:p>'


def _build(tmp_path, name, sections) -> str:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        for i, paras in enumerate(sections):
            sec = f'<hp:sec {_NS}>{"".join(paras)}</hp:sec>'
            zf.writestr(f"Contents/section{i}.xml", sec)
    return str(path)


def _page_count(path: str) -> int:
    return HwpxParser().parse(path, _meta()).file_meta.page_count


def test_synth_vertpos_reset_two_pages(tmp_path):
    # 0→2000 후 100 으로 리셋(<0.6×) → 2페이지
    path = _build(tmp_path, "reset.hwpx", [[_p([0, 1000, 2000]), _p([100, 1100])]])
    assert _page_count(path) == 2


def test_synth_three_pages(tmp_path):
    path = _build(tmp_path, "three.hwpx",
                  [[_p([0, 5000, 10000, 200, 6000, 300, 7000])]])
    assert _page_count(path) == 3


def test_synth_multisection_sum(tmp_path):
    # sec0: 리셋 1회(2p) + sec1: 하드 페이지브레이크(2p) = 4
    path = _build(tmp_path, "multi.hwpx", [
        [_p([0, 1000, 2000]), _p([100, 1100])],
        [_p(None), _p(None, page_break=True)],
    ])
    assert _page_count(path) == 4


def test_synth_cumulative_no_false_reset(tmp_path):
    # 단조 증가(리셋 없음) → 1페이지 (과다 카운트 방지)
    path = _build(tmp_path, "cumul.hwpx",
                  [[_p([0, 1000, 2000, 3000, 4000, 5000])]])
    assert _page_count(path) == 1


def test_synth_no_layout_cache_fallback(tmp_path):
    # lineseg 없음(캐시 부재) → 하한선 1 (크래시 없이 폴백)
    path = _build(tmp_path, "nocache.hwpx", [[_p(None), _p(None)]])
    assert _page_count(path) == 1


def test_synth_bad_zip_raises(tmp_path):
    path = tmp_path / "bad.hwpx"
    path.write_bytes(b"not a zip")
    with pytest.raises(RuntimeError, match="E0202"):
        HwpxParser().parse(str(path), _meta())


def test_synth_no_false_undercount_warning(tmp_path, caplog):
    # 표 없는 일반 문서는 과소집계 경고가 뜨면 안 됨(false positive 가드)
    path = _build(tmp_path, "plain.hwpx", [[_p([0, 1000, 2000]), _p([100, 1100])]])
    with caplog.at_level(logging.WARNING):
        HwpxParser().parse(path, _meta())
    assert not any(RISK_MARKER in r.getMessage() for r in caplog.records)
