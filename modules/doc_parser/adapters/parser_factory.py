"""
REQ-006 doc_parser — adapters/parser_factory.py

ParserFactory
MIME 타입 기준으로 적절한 파서 선택 + 인터리빙 래핑

변경 이력:
    v1.0.0 - 기본 파서 등록/선택
    v2.0.0 - 인터리빙 파서 자동 래핑 추가
             (TableDetector + VisionExtractor 조립)

포맷별 전략:
    그룹 A (감지 후 찰칵): PDF, HWPX, PPTX → InterleavingParser 래핑
    그룹 B (텍스트 기반):  DOCX → XML 순회 (비전 불필요)
                          HWP  → hwp5html primary + hwp5txt fallback (LibreOffice 드랍)
    그룹 C (3층 구조):    XLSX            → 기존 XlsxParser 유지
    그룹 D (비전 스킵):   CSV, MD         → 기존 파서 그대로

사용 예시:
    # 비전 미사용 (테스트/폴백)
    factory = ParserFactory()
    factory.register(PdfParser())

    # yaml 설정값으로 생성 (권장)
    factory = ParserFactory.from_yaml("config/parser_quality.yaml", llm=composition_root_llm)
    factory.register(PdfParser())
    parser = factory.get("application/pdf")
    # → InterleavingParser(PdfParser, TableDetector, VisionExtractor(llm))
"""
from __future__ import annotations

from pathlib import Path

import yaml

from doc_parser.adapters.interleaving_parser import InterleavingParser
from doc_parser.adapters.vision.table_detector import TableDetector
from doc_parser.adapters.vision.vision_extractor import VisionExtractor
from doc_parser.domain.ports.parser_port import ParserPort
from doc_parser.domain.ports.vision_port import VisionPort

# 인터리빙 래핑 제외 포맷 (그룹 C, D)
# XlsxParser는 3층 구조로 별도 처리
# CSV/MD는 구조적 파싱으로 비전 불필요
_INTERLEAVING_SKIP_MIME = {
    "text/csv",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ParserFactory:
    """파서 선택 + 인터리빙 조립 팩토리.

    ParserPort 구현체를 등록하고 MIME 타입에 맞는 파서를 반환.
    비전 모드가 활성화된 경우 InterleavingParser로 자동 래핑.

    Args:
        llm: LLMBase Modal Cls 인스턴스
            None이면 비전 미사용 (기존 파서 그대로 반환)
        broken_char_threshold: TableDetector 깨진 문자 임계값
            parser_quality.yaml의 broken_char_warn 값을 주입

    Raises:
        ValueError: 지원하지 않는 MIME 타입 (E0201)
    """

    def __init__(
        self,
        llm=None,
        broken_char_threshold: float = 0.1,
    ) -> None:
        self._parsers: list[ParserPort] = []
        self._llm = llm
        self._broken_char_threshold = broken_char_threshold

        # 비전 모드 컴포넌트 — llm이 있을 때만 활성화
        if llm is not None:
            self._table_detector = TableDetector(
                broken_char_threshold=broken_char_threshold
            )
            self._vision_extractor = VisionExtractor(llm=llm)
        else:
            self._table_detector = None
            self._vision_extractor = None

    @classmethod
    def from_yaml(
        cls,
        config_path: str | Path,
        llm=None,
    ) -> "ParserFactory":
        """parser_quality.yaml에서 설정값을 읽어 ParserFactory 생성.

        Args:
            config_path: parser_quality.yaml 경로
            llm: LLMBase Modal Cls 인스턴스

        Returns:
            ParserFactory: yaml 설정값이 주입된 팩토리

        Raises:
            FileNotFoundError: yaml 파일 없음
            KeyError: broken_char_warn 키 없음
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"parser_quality.yaml 없음: {path}")

        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if "broken_char_warn" not in config:
            raise KeyError("parser_quality.yaml에 broken_char_warn 키 없음")

        return cls(
            llm=llm,
            broken_char_threshold=config["broken_char_warn"],
        )

    def register(self, parser: ParserPort) -> None:
        """파서 등록.

        Args:
            parser: 등록할 ParserPort 구현체
        """
        self._parsers.append(parser)

    def get(self, mime_type: str) -> ParserPort:
        """MIME 타입에 맞는 파서 반환.

        비전 모드 활성화 + 인터리빙 대상 포맷이면
        InterleavingParser로 자동 래핑해서 반환.

        Args:
            mime_type: 파일 MIME 타입

        Returns:
            ParserPort: 해당 MIME 타입을 지원하는 파서
                비전 활성화 시 InterleavingParser 래핑 반환

        Raises:
            ValueError: 지원하지 않는 MIME 타입 (E0201)
        """
        base_parser = self._find_parser(mime_type)

        # 비전 미사용 or 스킵 포맷 → 기존 파서 그대로
        if self._llm is None or mime_type in _INTERLEAVING_SKIP_MIME:
            return base_parser

        # 인터리빙 래핑
        return InterleavingParser(
            base_parser=base_parser,
            table_detector=self._table_detector,
            vision_extractor=self._vision_extractor,
        )

    def supports(self, mime_type: str) -> bool:
        """해당 MIME 타입을 지원하는 파서가 있는지 확인."""
        return any(p.supports(mime_type) for p in self._parsers)

    @property
    def registered_parsers(self) -> list[ParserPort]:
        """등록된 파서 목록."""
        return list(self._parsers)

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _find_parser(self, mime_type: str) -> ParserPort:
        """MIME 타입에 맞는 BaseParser 탐색.

        Raises:
            ValueError: 지원하지 않는 MIME 타입 (E0201)
        """
        for parser in self._parsers:
            if parser.supports(mime_type):
                return parser
        raise ValueError(f"E0201: 지원하지 않는 파일 형식 — {mime_type}")
