# REQ-006 doc-parser — 구현 플랜

> 작성자: 김진형 (REQ-006)
> 작성일: 2026-05-07
> 최종 수정: 2026-05-07 (v2.5 반영)
> 대상 범위: `modules/doc-parser/` 전체
> 참고 문서: `MONOREPO_STRUCTURE.md`, `modules/doc-parser/README.md`, `REQ-006_v2_5.md`, `CLAUDE.md`

---

## 1. 왜 Domain 먼저인가?

```
Port(ABC) 계약이 확정되어야
  → 다른 모듈(ai-agent, storage)이 의존 가능
  → adapter/use_case와 독립적으로 테스트 가능
  → common-schemas import 경로 확정
```

---

## 2. 클래스 목록

### 반드시 구현해야 하는 클래스 (REQ-006이 만드는 것)

| 파일 | 클래스 | 설명 |
|------|--------|------|
| `entities/warning.py` | `WarningInfo` | 파싱 경고 정보 |
| `entities/warning.py` | `ElapsedDetail` | 단계별 처리 시간 (5단계) |
| `entities/chunk.py` | `ChunkOverlapMeta` | 청크 오버랩 메타 |
| `entities/chunk.py` | `Chunk` | 청킹 결과 단위 엔티티 |
| `value_objects/quality.py` | `QualityMetrics` | 품질 측정 지표 VO |
| `value_objects/quality.py` | `QualityGateResult` | 품질 게이트 결과 VO |
| `ports/parser_port.py` | `ParserPort` | 파서 ABC 계약 |
| `services/normalizer.py` | `Normalizer` | 기본 정규화 서비스 (v2.3 신규) |
| `services/chunking_service.py` | `ChunkingService` | 청킹 비즈니스 로직 |
| `services/quality_gate.py` | `QualityGate` | 품질 게이트 비즈니스 로직 |
| `services/pii_masking_service.py` | `PIIMaskingService` | PII 마스킹 비즈니스 로직 |
| `application/use_cases/parse_document.py` | `ParseDocumentUseCase` | 파싱 유스케이스 ✅ |
| `application/use_cases/extract_chunks.py` | `ExtractChunksUseCase` | 청킹 유스케이스 ✅ |
| `adapters/parsers/pdf_parser.py` | `PdfParser` | PDF 파서 구현체 |
| `adapters/parsers/docx_parser.py` | `DocxParser` | Word 파서 구현체 |
| `adapters/parsers/xlsx_parser.py` | `XlsxParser` | Excel 파서 구현체 |
| `adapters/parsers/csv_parser.py` | `CsvParser` | CSV 파서 구현체 |
| `adapters/parsers/pptx_parser.py` | `PptxParser` | PowerPoint 파서 구현체 |
| `adapters/parsers/hwp_parser.py` | `HwpParser` | HWP 파서 구현체 |
| `adapters/parsers/hwpx_parser.py` | `HwpxParser` | HWPX 파서 구현체 |
| `adapters/parsers/parser_factory.py` | `ParserFactory` | 파서 선택 팩토리 |

---

### 반드시 사용해야 하는 클래스 (common-schemas에서 import)

```python
from common_schemas.document import (
    BBox,          # 좌표 정보 (x1, y1, x2, y2)
    SheetMeta,     # 엑셀 시트 정보
    SourceRef,     # 블록/청크 출처 추적
    FileMeta,      # 파일 메타데이터
    ParserMeta,    # 파서 메타데이터 (REQ-012 간소화 버전)
    ContentBlock,  # 문서 블록 단위
    DocumentBlock, # 문서 전체 단위
)
```

| 클래스 | 어디서 쓰나 |
|--------|------------|
| `BBox` | `SourceRef` 내부, 블록 위치 추적 |
| `SheetMeta` | `FileMeta` 내부, 엑셀 시트 정보 |
| `SourceRef` | `Chunk.source_ref` 필드 |
| `FileMeta` | `DocumentBlock.file_meta`, `ParserPort.parse()` 인자 |
| `ParserMeta` | `DocumentBlock.parser` 필드 |
| `ContentBlock` | `ChunkingService`, `QualityGate` 입력값 |
| `DocumentBlock` | `ParserPort` 반환값, 모든 서비스 입력값 |

---

## 3. 외부 의존 관계

```
common_schemas.document (REQ-012 SSOT)
  └── BBox, SheetMeta, SourceRef
  └── FileMeta, ParserMeta
  └── ContentBlock, DocumentBlock

doc-parser/domain/ (본 플랜 범위)
  └── entities/       ← Chunk, WarningInfo, ElapsedDetail
  └── value_objects/  ← QualityGateResult, QualityMetrics
  └── ports/          ← ParserPort (ABC)
  └── services/       ← Normalizer, ChunkingService, QualityGate, PIIMaskingService
```

> **domain/ 레이어 import 금지 목록** (MONOREPO_STRUCTURE.md §14 기준)
> - `pdfplumber`, `python-docx`, `openpyxl` 등 파서 라이브러리 ❌
> - `sqlalchemy`, `fastapi`, `celery` 등 프레임워크 ❌
> - `modules/*/adapters/` 방향 import ❌
> - 순수 Python + Pydantic v2 + common_schemas만 ✅

---

## 4. 파일 구조

```
modules/doc-parser/
├── __init__.py
├── pyproject.toml                 ← ✅ 완료
├── config/
│   └── parser_quality.yaml        ← ✅ 완료 (품질 게이트 임계값)
├── domain/
│   ├── __init__.py                ← ✅ 완료
│   ├── entities/
│   │   ├── __init__.py            ← ✅ 완료
│   │   ├── chunk.py               ← ✅ 완료 (Chunk, ChunkOverlapMeta)
│   │   └── warning.py             ← ✅ 완료 (WarningInfo, ElapsedDetail)
│   ├── value_objects/
│   │   ├── __init__.py            ← ✅ 완료
│   │   └── quality.py             ← ✅ 완료 (QualityGateResult VO, QualityMetrics)
│   ├── services/
│   │   ├── __init__.py            ← ✅ 완료
│   │   ├── normalizer.py          ← 🔜 미구현 (v2.3 신규)
│   │   ├── chunking_service.py    ← ✅ 완료
│   │   ├── quality_gate.py        ← ✅ 완료
│   │   └── pii_masking_service.py ← ✅ 완료
│   └── ports/
│       ├── __init__.py            ← ✅ 완료
│       └── parser_port.py         ← ✅ 완료 (ParserPort ABC)
├── application/
│   └── use_cases/
│       ├── __init__.py            ← ✅ 완료
│       ├── parse_document.py      ← ✅ 완료 (ParseDocumentUseCase)
│       └── extract_chunks.py      ← ✅ 완료 (ExtractChunksUseCase)
├── adapters/
│   └── parsers/
│       ├── __init__.py            ← 🔜 미구현
│       ├── parser_factory.py      ← 🔜 미구현
│       ├── pdf_parser.py          ← 🔜 미구현
│       ├── docx_parser.py         ← 🔜 미구현
│       ├── xlsx_parser.py         ← 🔜 미구현
│       ├── csv_parser.py          ← 🔜 미구현
│       ├── pptx_parser.py         ← 🔜 미구현
│       ├── hwp_parser.py          ← 🔜 미구현
│       └── hwpx_parser.py         ← 🔜 미구현
└── tests/
    ├── conftest.py                ← ✅ 완료
    ├── unit/
    │   ├── domain/                ← ✅ 완료 (51 passed)
    │   └── application/           ← 🔜 미구현
    └── integration/
        └── adapters/              ← 🔜 미구현 (파서 구현체 테스트)
```

---

## 5. 개발 규칙 (CLAUDE.md 기준)

### 5-1. 의존성 방향 (절대 위반 금지)

```
common_schemas        ← 최내곽 (Pydantic만 의존)
      ↑
domain/               ← common_schemas + 자기 도메인만 import
      ↑
application/          ← domain/* + Port 인터페이스만
      ↑
adapters/             ← domain/ports + 외부 파서 라이브러리
```

### 5-2. doc-parser Port → Adapter 매핑

| Port (ABC) 정의 위치 | Adapter 구현 위치 |
|--------------------|----------------|
| `doc-parser/domain/ports/ParserPort` | `doc-parser/adapters/parsers/` |

### 5-3. 절대 금지 import 패턴

```python
# ❌ domain에서 파서 라이브러리 import
from pdfplumber import ...     # adapters/에서만 허용
from docx import ...           # adapters/에서만 허용
from openpyxl import ...       # adapters/에서만 허용

# ❌ domain/application에서 프레임워크 import
from fastapi import ...        # api-server에서만 허용
from sqlalchemy import ...     # storage에서만 허용

# ❌ application에서 구체 Adapter 직접 import
from doc_parser.adapters.parsers.pdf_parser import PdfParser  # Port ABC만 참조
```

### 5-4. 새 코드 작성 절차

1. **README 읽기** — `modules/doc-parser/README.md` 먼저 확인
2. **의존성 확인** — 위 의존성 방향 규칙에 따라 import 가능 여부 확인
3. **레이어 배치** — `domain` / `application` / `adapters` 중 어디인지 판단
4. **공유 타입 사용** — 엔티티/VO는 반드시 `common_schemas`에서 import
5. **Port 분리** — 인터페이스는 `domain/ports/`, 구현은 `adapters/parsers/`
6. **보안 점검** — 하드코딩 금지, 임계값은 `config/parser_quality.yaml`에서 읽기

### 5-5. 컨벤션

- Python >= 3.11, Ruff lint (`line-length=120`)
- 타입 힌트 필수 (모든 함수 시그니처)
- ID 필드: `UUID` 타입 사용
- VO(Value Object): `frozen=True` 필수 (`QualityMetrics`, `QualityGateResult`)
- 환경 변수: 하드코딩 금지, `os.getenv()` 사용
- 임계값: 코드 내 숫자 직접 기입 금지 → `config/parser_quality.yaml`에서 읽기

---

## 6. entities/ 상세 설계

### 6-1. warning.py

```python
from typing import Optional
from pydantic import BaseModel

# WarningInfo: 파싱 중 발생한 경고 정보
class WarningInfo(BaseModel):
    code: str                      # 에러코드 (E0201 등)
    message: str                   # 사용자 메시지
    detail: Optional[dict] = None  # 추가 정보

# ElapsedDetail: 단계별 처리 시간 (5단계)
class ElapsedDetail(BaseModel):
    parse_ms: int = 0
    normalize_ms: int = 0
    masking_ms: int = 0
    chunking_ms: int = 0
    quality_gate_ms: int = 0
```

### 6-2. chunk.py

```python
from __future__ import annotations
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel
from common_schemas.document import SourceRef

# ChunkOverlapMeta: 오버랩 정보
class ChunkOverlapMeta(BaseModel):
    has_overlap: bool
    overlap_tokens: Optional[int] = None

# Chunk: 청킹 결과 단위
# importance_score → REQ-004 AI_Agent가 채움 (파서는 None으로 둠)
class Chunk(BaseModel):
    chunk_id: UUID
    chunk_type: Literal["structural", "page", "token", "table"]
    content: str
    token_count: int
    source_ref: SourceRef
    overlap_meta: Optional[ChunkOverlapMeta] = None
    block_ids: list[UUID]
    importance_score: Optional[float] = None  # REQ-004 담당
```

---

## 7. value_objects/ 상세 설계

### 7-1. quality.py

```python
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict
from doc_parser.domain.entities.warning import WarningInfo

# QualityMetrics: 품질 측정 지표 VO
class QualityMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)  # VO → 불변

    korean_ratio: float
    broken_char_ratio: float
    blocks_per_page: float
    heading_ratio: float
    valid_table_ratio: float
    structural_chunk_ratio: float
    total_chunks: int
    avg_tokens: float

# QualityGateResult: 품질 게이트 결과 VO
class QualityGateResult(BaseModel):
    model_config = ConfigDict(frozen=True)  # VO → 불변

    quality_status: Literal[
        "success",
        "warning",
        "manual_correction_required",
        "failed"
    ]
    metrics: QualityMetrics
    warnings: list[WarningInfo]
    error_codes: list[str]
    decision_reason: Optional[str] = None
```

---

## 8. ports/ 상세 설계

### 8-1. parser_port.py

```python
from abc import ABC, abstractmethod
from common_schemas.document import DocumentBlock, FileMeta

# ParserPort: 파서 구현체가 따라야 할 ABC 계약
class ParserPort(ABC):

    @abstractmethod
    def parse(
        self,
        file_path: str,
        file_meta: FileMeta
    ) -> DocumentBlock:
        """문서 파싱 → DocumentBlock 반환"""
        ...

    @abstractmethod
    def supports(self, mime_type: str) -> bool:
        """이 파서가 해당 MIME 타입을 지원하는지"""
        ...
```

> `adapters/parsers/` 의 PdfParser, DocxParser 등이 이 포트를 구현

---

## 9. services/ 상세 설계

### 9-1. normalizer.py (v2.3 신규)

```python
class Normalizer:
    """
    기본 정규화 서비스
    처리 순서: 파싱 직후, PII 마스킹 이전
    HWP/HWPX 전처리: preprocess_hwp_text() 적용
    """
    def normalize_document(self, doc: DocumentBlock) -> DocumentBlock: ...
    def normalize_block(self, block: ContentBlock) -> ContentBlock: ...
    def preprocess_hwp_text(self, text: str) -> str: ...
```

### 9-2. chunking_service.py

```python
class ChunkingService:
    """
    청킹 전략 (우선순위):
    1순위: 구조적 분할 (heading 기준)
    2순위: 물리적 분할 (page 기준)
    3순위: 토큰 최적화 (RecursiveCharacterTextSplitter)
    4순위: 표 특수 처리 (독립 청크, 오버랩 없음)
    """
    def chunk(self, document: DocumentBlock, strategy: Optional[str] = None) -> list[Chunk]: ...
    def _chunk_by_section(self, blocks: list[ContentBlock]) -> list[Chunk]: ...
    def _chunk_by_page(self, blocks: list[ContentBlock]) -> list[Chunk]: ...
    def _chunk_by_token(self, blocks: list[ContentBlock]) -> list[Chunk]: ...
    def _chunk_table(self, block: ContentBlock) -> list[Chunk]: ...
    def _apply_overlap(self, chunks: list[Chunk]) -> list[Chunk]: ...
    def _calc_token_count(self, text: str) -> int: ...
```

### 9-3. quality_gate.py

```python
class QualityGate:
    """
    모든 임계값은 config/parser_quality.yaml에서 읽음
    코드 내 숫자 직접 기입 금지!
    """
    def __init__(self, config: dict): ...
    def evaluate(self, document: DocumentBlock, chunks: list[Chunk]) -> QualityGateResult: ...
    def _calc_korean_ratio(self, text: str) -> float: ...
    def _calc_broken_char_ratio(self, text: str) -> float: ...
    def _calc_heading_ratio(self, blocks: list[ContentBlock]) -> float: ...
    def _calc_valid_table_ratio(self, blocks: list[ContentBlock]) -> float: ...
    def _calc_structural_chunk_ratio(self, chunks: list[Chunk]) -> float: ...
```

### 9-4. pii_masking_service.py

```python
class PIIMaskingService:
    """
    PII 마스킹 순서: 정규화 이후, 청킹 이전
    MVP: 단방향 마스킹만 지원 (원복 불가)
    """
    PATTERNS = {
        "rrn":     (r"\d{6}-[1-4]\d{6}",                    "[MASKED_RRN]"),
        "phone":   (r"0\d{1,2}-\d{3,4}-\d{4}",              "[MASKED_PHONE]"),
        "email":   (r"[\w.]+@[\w.]+",                        "[MASKED_EMAIL]"),
        "account": (r"\d{3,4}-\d{2,6}-\d{5,7}",             "[MASKED_ACCOUNT]"),
        "card":    (r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}", "[MASKED_CARD]"),
    }

    def mask_text(self, text: str) -> tuple[str, list[WarningInfo]]: ...
    def mask_block(self, block: ContentBlock) -> tuple[ContentBlock, list[WarningInfo]]: ...
    def mask_document(self, doc: DocumentBlock) -> tuple[DocumentBlock, list[WarningInfo]]: ...
    def is_allow_listed(self, text: str) -> bool: ...
```

---

## 10. adapters/ 상세 설계

### 10-1. 파서 라이브러리 확정 (REQ-006_v2_5 §4 기준)

| 파서 | 라이브러리 | 비고 |
|------|----------|------|
| `PdfParser` | `PyMuPDF(fitz)` + `pdfplumber` | 본문: fitz, 표: pdfplumber(보조) |
| `DocxParser` | `python-docx` | 서식 보존 제외 |
| `XlsxParser` | `openpyxl` | `read_only=True` 모드 권장 |
| `CsvParser` | `pandas` | 인코딩 오류 처리 필요 |
| `PptxParser` | `python-pptx` | 이미지 내 텍스트 제외 |
| `HwpParser` | `pyhwp / hwp5txt` | 표·서식·각주 제한 |
| `HwpxParser` | `python-hwpx / ZIP·XML` | 복잡 표·서식 제한, POC 검증 선행 필요 |

### 10-2. PdfParser 특이사항

```python
class PdfParser(ParserPort):
    def parse(self, file_path: str, file_meta: FileMeta) -> DocumentBlock:
        # is_scanned_pdf() 먼저 실행
        # True → E0212 + 에러 반환
        ...

    def is_scanned_pdf(self, file_path: str) -> bool:
        """
        PyMuPDF로 첫 3페이지 텍스트 추출 시도
        텍스트 비율이 임계값 미만이면 스캔 PDF로 판단
        → True: 스캔 PDF (E0212 처리)
        → False: 텍스트 기반 PDF (정상 파싱)
        """
        ...
```

### 10-3. ParserFactory

```python
class ParserFactory:
    _registry: list[ParserPort] = []

    @classmethod
    def register(cls, parser: ParserPort) -> None: ...

    @classmethod
    def get(cls, mime_type: str) -> ParserPort:
        # mime_type 기준으로 파서 선택
        # 없으면 ValueError(E0201)
        ...
```

---

## 11. 구현 순서

```
✅ Step 1:  domain/entities/warning.py
✅ Step 2:  domain/entities/chunk.py
✅ Step 3:  domain/entities/__init__.py
✅ Step 4:  domain/value_objects/quality.py
✅ Step 5:  domain/value_objects/__init__.py
✅ Step 6:  domain/ports/parser_port.py
✅ Step 7:  domain/ports/__init__.py
✅ Step 8:  domain/services/pii_masking_service.py
✅ Step 9:  domain/services/chunking_service.py
✅ Step 10: domain/services/quality_gate.py
✅ Step 11: domain/services/__init__.py
✅ Step 12: domain/__init__.py
✅ Step 13: config/parser_quality.yaml
✅ Step 14: application/use_cases/parse_document.py
✅ Step 15: application/use_cases/extract_chunks.py
✅ Step 16: application/use_cases/__init__.py
🔜 Step 17: domain/services/normalizer.py
🔜 Step 18: adapters/parsers/parser_factory.py
🔜 Step 19: adapters/parsers/pdf_parser.py
🔜 Step 20: adapters/parsers/docx_parser.py
🔜 Step 21: adapters/parsers/xlsx_parser.py
🔜 Step 22: adapters/parsers/csv_parser.py
🔜 Step 23: adapters/parsers/pptx_parser.py
🔜 Step 24: adapters/parsers/hwp_parser.py
🔜 Step 25: adapters/parsers/hwpx_parser.py
🔜 Step 26: adapters/parsers/__init__.py
```

---

## 12. 테스트 계획

```
tests/
├── conftest.py                    ← ✅ 완료
├── unit/
│   ├── domain/                    ← ✅ 완료 (51 passed)
│   │   ├── test_chunk.py
│   │   ├── test_quality.py
│   │   ├── test_pii_masking.py
│   │   ├── test_chunking_service.py
│   │   └── test_quality_gate.py
│   └── application/               ← 🔜 미구현
└── integration/
    └── adapters/                  ← 🔜 미구현 (파서 구현체 테스트)
```

| 테스트 대상 | 주요 케이스 |
|------------|------------|
| `Chunk` | UUID 자동생성, importance_score=None 기본값 |
| `QualityGateResult` | status 4종, warning 누적 → manual_correction_required 격상 |
| `PIIMaskingService` | RRN/전화/이메일/계좌/카드 마스킹, allow-list |
| `ChunkingService` | 4가지 전략 우선순위 |
| `QualityGate` | yaml 설정값 기반 판단 |
| `PdfParser` | 스캔 PDF 감지 → E0212, 정상 PDF 파싱 |
| `ParseDocumentUseCase` | 파서 선택, PII 마스킹, 품질 검증 흐름 |
| `ExtractChunksUseCase` | 청킹 결과, importance_score=None |

---

## 13. 미확정 항목

| 항목 | 내용 | 협의 대상 |
|------|------|----------|
| `ChunkingService` 토큰 계산 | 폐쇄망 tiktoken 불가 시 `char × 0.7` 전환 | config/parser_quality.yaml |
| PII Allow-list 패턴 | 하네스 엔지니어링 일련번호 오검출 방지 | 황대원님 협의 필요 |
| `importance_score` 계산 시점 | REQ-004 AI_Agent 담당 확인 완료 ✅ | 신정혜님 확인됨 |
| `HandoffPayload` 구조 | AI_Agent로 넘기는 데이터 필드 정의 | 황대원님 (REQ-012 SSOT) |
| `HWPX` POC 검증 | `python-hwpx / ZIP·XML` 실제 동작 확인 필요 | 내부 |
| `Normalizer` 메서드 목록 | v2.3 기준 6개 메서드 확정 필요 | 내부 |