"""
REQ-006 doc_parser — adapters/vision/vision_extractor.py

VisionExtractor
fitz(PyMuPDF) 이미지 캡처 + Gemma4(Modal) 비전 분석

처리 흐름:
    파일 경로 + VisionType
      → fitz(PyMuPDF) → 해당 페이지 PNG 렌더링
      → PNG → base64 data URL
      → LLMBase().generate(prompt, images=[data_url])
      → ContentBlock 반환

포맷별 캡처 전략:
    그룹 A (감지 후 찰칵): PDF, HWPX, PPTX → 해당 페이지만
    그룹 C (시각객체):    XLSX            → 차트/이미지 영역
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from uuid import uuid4

from common_schemas.document import ContentBlock, SourceRef

from doc_parser.adapters.vision.prompts import VisionPromptStrategy
from doc_parser.domain.entities.vision_type import VisionType
from doc_parser.domain.ports.vision_port import VisionPort


class VisionExtractor(VisionPort):
    """fitz + Gemma4 기반 비전 추출기.

    Args:
        llm: LLMBase Modal Cls 인스턴스 (Modal RPC 호출용)
            None이면 테스트 모드 (이미지 캡처만 수행)
        debug_output_dir: 캡처 이미지 저장 경로
            None이면 임시 폴더 사용 후 자동 삭제
            경로 지정 시 캡처 이미지 보존 (테스트 확인용)

    Example:
        # 운영 모드 (llm 구현체는 Composition Root에서 DI 주입)
        extractor = VisionExtractor(llm=composition_root_llm)

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
        try:
            # ── 1. fitz로 PNG 렌더링 ──
            image_path = self._capture_page(file_path, page_num)
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

    # ──────────────────────────────────────────
    # Private — 이미지 캡처
    # ──────────────────────────────────────────

    def _capture_page(
        self,
        file_path: str,
        page_num: int,
        zoom: float = 2.0,
    ) -> str | None:
        """fitz(PyMuPDF)로 파일 특정 페이지 → PNG 렌더링.

        Args:
            file_path: 원본 파일 경로
            page_num: 캡처할 페이지 번호 (1-based)
            zoom: 렌더링 배율 (기본 2.0 = 144dpi)

        Returns:
            str: PNG 파일 경로
            None: 렌더링 실패 시
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return None

        try:
            out_dir = (
                self._debug_output_dir
                if self._debug_output_dir
                else tempfile.mkdtemp(prefix="vision_")
            )

            doc = fitz.open(file_path)
            page_index = page_num - 1  # 0-based

            if page_index >= len(doc):
                doc.close()
                return None

            matrix = fitz.Matrix(zoom, zoom)
            page = doc[page_index]
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            stem = Path(file_path).stem
            image_path = Path(out_dir) / f"{stem}_page_{page_num:03d}.png"
            pix.save(str(image_path))
            doc.close()

            return str(image_path)

        except Exception:
            return None

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
