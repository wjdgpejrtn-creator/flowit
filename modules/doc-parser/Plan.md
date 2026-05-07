# REQ-006 doc-parser — Domain Layer 구현 플랜

> 작성자: 김진형 (REQ-006)
> 작성일: 2026-05-07
> 대상 범위: `modules/doc-parser/domain/` (entities + value_objects + ports + services)
> 참고 문서: `MONOREPO_STRUCTURE.md`, `modules/doc-parser/README.md`

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
| `entities/warning.py` | `ElapsedDetail` | 단계별 처리 시간 |
| `entities/chunk.py` | `ChunkOverlapMeta` | 청크 오버랩 메타 |
| `entities/chunk.py` | `Chunk` | 청킹 결과 단위 엔티티 |
| `value_objects/quality.py` | `QualityMetrics` | 품질 측정 지표 VO |
| `value_objects/quality.py` | `QualityGateResult` | 품질 게이트 결과 VO |
| `ports/parser_port.py` | `ParserPort` | 파서 ABC 계약 |
| `services/chunking_service.py` | `ChunkingService` | 청킹 비즈니스 로직 |
| `services/quality_gate.py` | `QualityGate` | 품질 게이트 비즈니스 로직 |
| `services/pii_masking_service.py` | `PIIMaskingService` | PII 마스킹 비즈니스 로직 |
| `adapters/parsers/` | `PdfParser` | PDF 파서 구현체 |
| `adapters/parsers/` | `DocxParser` | Word 파서 구현체 |
| `adapters/parsers/` | `XlsxParser` | Excel 파서 구현체 |
| `adapters/parsers/` | `CsvParser` | CSV 파서 구현체 |
| `adapters/parsers/` | `PptxParser` | PowerPoint 파서 구현체 |
| `adapters/parsers/` | `HwpParser` | HWP 파서 구현체 |
| `adapters/parsers/` | `HwpxParser` | HWPX 파서 구현체 |

> 현재 플랜 범위: `domain/` (entities + value_objects + ports + services)
> `adapters/` 는 다음 단계

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
  └── services/       ← ChunkingService, QualityGate, PIIMaskingService
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
├── domain/
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── chunk.py           ← Chunk, ChunkOverlapMeta
│   │   └── warning.py         ← WarningInfo, ElapsedDetail
│   ├── value_objects/
│   │   ├── __init__.py
│   │   └── quality.py         ← QualityGateResult VO, QualityMetrics
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chunking_service.py    ← ChunkingService
│   │   ├── quality_gate.py        ← QualityGate
│   │   └── pii_masking_service.py ← PIIMaskingService
│   └── ports/
│       ├── __init__.py
│       └── parser_port.py     ← ParserPort ABC
├── application/
│   └── use_cases/             ← 다음 단계
├── adapters/
│   └── parsers/               ← 다음 단계
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── domain/            ← domain 순수 테스트 (mock 불필요)
    │   └── application/       ← 유스케이스 테스트 (Port mock)
    └── integration/
        └── adapters/          ← 어댑터 통합 테스트
```

> **모노레포 표준 구조 준수** (MONOREPO_STRUCTURE.md §7 기준)
> - `entities/` → 모듈 전용 도메인 엔티티
> - `value_objects/` → QualityGateResult 등 불변 VO (frozen=True)
> - `services/` → 순수 비즈니스 로직
> - `ports/` → ABC 인터페이스 정의

---

## 5. entities/ 상세 설계

### 5-1. warning.py

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

### 5-2. chunk.py

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

## 6. value_objects/ 상세 설계

### 6-1. quality.py

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

## 7. ports/ 상세 설계

### 7-1. parser_port.py

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

## 8. services/ 상세 설계

### 8-1. chunking_service.py

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

### 8-2. quality_gate.py

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

### 8-3. pii_masking_service.py

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

## 9. 구현 순서

```
Step 1:  domain/entities/warning.py           (WarningInfo, ElapsedDetail)
Step 2:  domain/entities/chunk.py             (ChunkOverlapMeta, Chunk)
Step 3:  domain/entities/__init__.py          (export 정리)
Step 4:  domain/value_objects/quality.py      (QualityMetrics, QualityGateResult)
Step 5:  domain/value_objects/__init__.py
Step 6:  domain/ports/parser_port.py          (ParserPort ABC)
Step 7:  domain/ports/__init__.py
Step 8:  domain/services/pii_masking_service.py
Step 9:  domain/services/chunking_service.py
Step 10: domain/services/quality_gate.py
Step 11: domain/services/__init__.py
Step 12: domain/__init__.py                   (전체 export 정리)
```

---

## 10. 테스트 계획

```
tests/
├── conftest.py
├── unit/
│   └── domain/
│       ├── test_chunk.py
│       ├── test_quality.py
│       ├── test_pii_masking.py
│       ├── test_chunking_service.py
│       └── test_quality_gate.py
└── integration/
    └── adapters/          ← 다음 단계 (파서 구현체 테스트)
```

| 테스트 대상 | 주요 케이스 |
|------------|------------|
| `Chunk` | UUID 자동생성, importance_score=None 기본값 |
| `QualityGateResult` | status 4종, warning 누적 → manual_correction_required 격상 |
| `PIIMaskingService` | RRN/전화/이메일/계좌/카드 마스킹, allow-list |
| `ChunkingService` | 4가지 전략 우선순위 |
| `QualityGate` | yaml 설정값 기반 판단 |

---

## 11. 미확정 항목

| 항목 | 내용 | 협의 대상 |
|------|------|----------|
| `ChunkingService` 토큰 계산 | 폐쇄망 tiktoken 불가 시 `char × 0.7` 전환 | config/parser_quality.yaml |
| PII Allow-list 패턴 | 하네스 엔지니어링 일련번호 오검출 방지 | 황대원님 협의 필요 |
| `importance_score` 계산 시점 | REQ-004 AI_Agent 담당 확인 완료 ✅ | 신정혜님 확인됨 |