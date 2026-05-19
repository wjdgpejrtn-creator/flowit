"""
REQ-006 doc_parser — adapters/vision/vision_extractor.py

VisionExtractor
LibreOffice 이미지 캡처 + Gemma4(Modal) 비전 분석

처리 흐름:
    파일 경로 + VisionType
      → LibreOffice --headless → PNG 변환
      → PNG → base64 data URL
      → LLMBase().generate(prompt, images=[data_url])
      → ContentBlock 반환

포맷별 캡처 전략:
    그룹 A (감지 후 찰칵): PDF, HWPX, PPTX → 해당 페이지만
    그룹 B (전체 찰칵):   DOCX, HWP       → 전체 페이지
    그룹 C (시각객체):    XLSX            → 차트/이미지 영역
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from common_schemas.document import ContentBlock, SourceRef

from doc_parser.domain.entities.vision_type import VisionPromptStrategy, VisionType
from doc_parser.domain.ports.vision_port import VisionPort

# LibreOffice 실행 경로 — 환경변수로 오버라이드 가능
# 로컬 Windows: C:\Program Files\LibreOffice\program\soffice.exe
# 서버 Linux:   soffice (PATH에 있음)
_SOFFICE_PATH = os.environ.get(
    "SOFFICE_PATH",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
)

# LibreOffice 변환 타임아웃 (초)
_CONVERT_TIMEOUT = 60


class VisionExtractor(VisionPort):
    """LibreOffice + Gemma4 기반 비전 추출기.

    Args:
        llm: LLMBase Modal Cls 인스턴스 (Modal RPC 호출용)
            None이면 테스트 모드 (이미지 캡처만 수행)
        debug_output_dir: 캡처 이미지 저장 경로
            None이면 임시 폴더 사용 후 자동 삭제
            경로 지정 시 캡처 이미지 보존 (테스트 확인용)

    Example:
        # 운영 모드
        extractor = VisionExtractor(llm=LLMBase())

        # 테스트 모드 — 캡처 이미지 확인
        extractor = VisionExtractor(
            llm=None,
            debug_output_dir="tests/vision_debug"
        )
    """

    def __init__(
        self,
        llm=None,
        debug_output_dir: str | None = None,
    ) -> None:
        self._llm = llm
        # debug_output_dir 있으면 폴더 생성 후 캡처 이미지 보존
        # None이면 임시 폴더 사용 후 자동 삭제
        if debug_output_dir:
            Path(debug_output_dir).mkdir(parents=True, exist_ok=True)
        self._debug_output_dir = debug_output_dir

    def extract(
        self,
        file_path: str,
        vision_type: VisionType,
        page_num: int = 1,
        block_index: int = 0,
    ) -> ContentBlock | None:
        """파일의 특정 페이지를 찰칵📸하고 Gemma4로 텍스트 추출.

        Args:
            file_path: 원본 파일 경로
            vision_type: 비전 추출 유형 (프롬프트 결정)
            page_num: 캡처할 페이지 번호 (1-based)
            block_index: ContentBlock 순서 인덱스

        Returns:
            ContentBlock: 비전 추출 결과
            None: 캡처 또는 추출 실패 시
        """
        out_dir = None
        try:
            # ── 1. LibreOffice로 PNG 변환 ──
            image_path, out_dir = self._capture_page(file_path, page_num)
            if not image_path:
                return None

            # ── 2. PNG → base64 data URL ──
            data_url = self._to_data_url(image_path)

            # ── 3. Gemma4 호출 ──
            content = self._call_gemma4(data_url, vision_type)

            if not content:
                return None

            return ContentBlock(
                block_id=uuid4(),
                block_type=vision_type.to_block_type(),
                content=content,
                page=page_num,
                source_ref=SourceRef(
                    page=page_num,
                    block_index=block_index,
                ),
            )

        except Exception:
            # 비전 추출 실패 → None 반환 (InterleavingParser가 warning 처리)
            return None

        finally:
            # ── 4. 이미지 정리 ──
            # debug_output_dir 없으면 임시 폴더째 삭제
            # debug_output_dir 있으면 보존 (테스트 확인용)
            if out_dir and not self._debug_output_dir:
                shutil.rmtree(out_dir, ignore_errors=True)


    def extract_all_pages(
        self,
        file_path: str,
        vision_type: VisionType,
        start_block_index: int = 0,
        max_pages: int | None = None,
    ) -> list[ContentBlock]:
        """파일 전체 페이지를 PDF→PNG로 렌더링한 뒤 페이지별 Gemma4 분석.

        HWP처럼 텍스트 파서가 page/표/이미지 구조를 알기 어려운 포맷의
        deep fallback 용도.
        """
        blocks: list[ContentBlock] = []
        out_dir = None

        try:
            pdf_path, out_dir = self._convert_to_pdf(file_path)
            if not pdf_path:
                return blocks

            image_paths = self._render_pdf_to_images(
                pdf_path=pdf_path,
                out_dir=out_dir,
                max_pages=max_pages,
            )

            for idx, image_path in enumerate(image_paths, start=1):
                data_url = self._to_data_url(image_path)
                content = self._call_gemma4(data_url, vision_type)

                if not content:
                    continue

                blocks.append(
                    ContentBlock(
                        block_id=uuid4(),
                        block_type=vision_type.to_block_type(),
                        content=content,
                        page=idx,
                        source_ref=SourceRef(
                            page=idx,
                            block_index=start_block_index + len(blocks),
                        ),
                    )
                )

            return blocks

        except Exception:
            return blocks

        finally:
            if out_dir and not self._debug_output_dir:
                shutil.rmtree(out_dir, ignore_errors=True)

    def _convert_to_pdf(
        self,
        file_path: str,
    ) -> tuple[str | None, str | None]:
        """LibreOffice headless로 파일 → PDF 변환."""
        try:
            out_dir = (
                self._debug_output_dir
                if self._debug_output_dir
                else tempfile.mkdtemp(prefix="vision_pdf_")
            )

            result = subprocess.run(
                [
                    _SOFFICE_PATH,
                    "--headless",
                    "--convert-to", "pdf",
                    file_path,
                    "--outdir", out_dir,
                ],
                capture_output=True,
                text=True,
                timeout=_CONVERT_TIMEOUT,
            )

            if result.returncode != 0:
                return None, out_dir

            stem = Path(file_path).stem
            pdf_path = Path(out_dir) / f"{stem}.pdf"

            if pdf_path.exists():
                return str(pdf_path), out_dir

            pdfs = sorted(Path(out_dir).glob("*.pdf"))
            if pdfs:
                return str(pdfs[0]), out_dir

            return None, out_dir

        except subprocess.TimeoutExpired:
            return None, None
        except Exception:
            return None, None

    def _render_pdf_to_images(
        self,
        pdf_path: str,
        out_dir: str,
        max_pages: int | None = None,
        zoom: float = 2.0,
    ) -> list[str]:
        """PDF 전체 페이지를 PNG 이미지로 렌더링."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return []

        image_paths: list[str] = []

        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            if max_pages is not None:
                total_pages = min(total_pages, max_pages)

            matrix = fitz.Matrix(zoom, zoom)
            stem = Path(pdf_path).stem

            for page_index in range(total_pages):
                page = doc[page_index]
                pix = page.get_pixmap(matrix=matrix, alpha=False)

                image_path = Path(out_dir) / f"{stem}_page_{page_index + 1:03d}.png"
                pix.save(str(image_path))
                image_paths.append(str(image_path))

            doc.close()
            return image_paths

        except Exception:
            return image_paths

    # ──────────────────────────────────────────
    # Private — 이미지 캡처
    # ──────────────────────────────────────────

    def _capture_page(
        self,
        file_path: str,
        page_num: int,
    ) -> tuple[str | None, str | None]:
        """LibreOffice headless로 파일 → PNG 변환.

        Args:
            file_path: 원본 파일 경로
            page_num: 캡처할 페이지 번호

        Returns:
            tuple: (PNG 파일 경로 or None, 출력 폴더 경로 or None)
        """
        try:
            # debug_output_dir 있으면 거기에 저장, 없으면 임시 폴더
            out_dir = (
                self._debug_output_dir
                if self._debug_output_dir
                else tempfile.mkdtemp(prefix="vision_")
            )

            result = subprocess.run(
                [
                    _SOFFICE_PATH,
                    "--headless",
                    "--convert-to", "png",
                    file_path,
                    "--outdir", out_dir,
                ],
                capture_output=True,
                text=True,
                timeout=_CONVERT_TIMEOUT,
            )

            if result.returncode != 0:
                return None, out_dir

            # LibreOffice는 파일명.png 로 저장
            # 멀티페이지 문서는 파일명1.png, 파일명2.png ...
            stem = Path(file_path).stem
            out_path = Path(out_dir)

            # 단일 페이지 파일 (DOCX 전체 = 1 PNG)
            single = out_path / f"{stem}.png"
            if single.exists():
                return str(single), out_dir

            # 멀티페이지 → 해당 페이지 선택
            paged = out_path / f"{stem}{page_num}.png"
            if paged.exists():
                return str(paged), out_dir

            # 첫 번째 PNG 폴백
            pngs = sorted(out_path.glob(f"{stem}*.png"))
            if pngs:
                idx = min(page_num - 1, len(pngs) - 1)
                return str(pngs[idx]), out_dir

            return None, out_dir

        except subprocess.TimeoutExpired:
            return None, None
        except Exception:
            return None, None

    # ──────────────────────────────────────────
    # Private — base64 변환
    # ──────────────────────────────────────────

    def _to_data_url(self, image_path: str) -> str:
        """PNG 파일 → base64 data URL 변환.

        Args:
            image_path: PNG 파일 경로

        Returns:
            str: "data:image/png;base64,..." 형식
        """
        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"

    # ──────────────────────────────────────────
    # Private — Gemma4 호출
    # ──────────────────────────────────────────

    def _call_gemma4(
        self,
        data_url: str,
        vision_type: VisionType,
    ) -> str | None:
        """Gemma4 Modal RPC 호출.

        Args:
            data_url: base64 PNG data URL
            vision_type: 프롬프트 선택 기준

        Returns:
            str: Gemma4 응답 텍스트
            None: LLM 미설정 또는 호출 실패
        """
        if self._llm is None:
            # 테스트 모드 — 이미지 캡처만 확인할 때
            return "[vision_test_mode]"

        try:
            prompt = VisionPromptStrategy.get(vision_type)
            result = self._llm.generate.remote(
                prompt,
                images=[data_url],
                max_tokens=1024,
                temperature=0.1,
            )
            return result.get("generated_text", "").strip() or None

        except Exception:
            return None
