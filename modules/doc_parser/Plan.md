# REQ-006 doc_parser — 구현 플랜

> 작성자: 김진형 (REQ-006)
> 작성일: 2026-05-07
> 최종 수정: 2026-05-07 (정적분석결과 + 명세서 반영)
> 대상 범위: `modules/doc_parser/` 전체
> 참고 문서: `MONOREPO_STRUCTURE.md`, `modules/doc_parser/README.md`, `REQ-006_v2_5.md`, `CLAUDE.md`, `정적분석결과_개선내역.md`

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
| `entities/chunk.py` | `ChunkingStrategy` | 청킹 전략 설정 VO |
| `entities/quality.py` | `QualityMetrics` | 품질 측정 지표 VO |
| `entities/quality.py` | `QualityGateResult` | 품질 게이트 결과 VO |
| `entities/quality.py` | `QualityConfig` | 품질 게이트 설정 VO (yaml 로드) |
| `entities/pii.py` | `PIIMaskRule` | PII 마스킹 규칙 정의 |
| `ports/parser_port.py` | `ParserPort` | 파서 ABC 계약 |
| `ports/repository_port.py` | `DocumentRepositoryPort` | 저장소 ABC 계약 |
| `ports/config_port.py` | `ConfigLoaderPort` | 설정 로더 ABC 계약 |
| `services/normalizer.py` | `NormalizationService` | 기본 정규화 서비스 |
| `services/chunking_service.py` | `ChunkingService` | 청킹 비즈니스 로직 |
| `services/quality_gate.py` | `QualityGate` | 품질 게이트 비즈니스 로직 |
| `services/pii_masking_service.py` | `PIIMaskingService` | PII 마스킹 비즈니스 로직 |
| `services/parser_factory.py` | `ParserFactory` | 파서 선택 팩토리 (domain/services/) |
| `application/use_cases/parse_document.py` | `ParseDocumentUseCase` | 파싱 유스케이스 ✅ |
| `application/use_cases/extract_chunks.py` | `ExtractChunksUseCase` | 청킹 유스케이스 ✅ |
| `application/use_cases/parsing_pipeline.py` | `ParsingPipeline` | 전체 파이프라인 오케스트레이션 |
| `adapters/parsers/pdf_parser.py` | `PdfParser` | PDF 파서 구현체 ✅ |
| `adapters/parsers/docx_parser.py` | `DocxParser` | Word 파서 구현체 ✅ |
| `adapters/parsers/xlsx_parser.py` | `XlsxParser` | Excel 파서 구현체 ✅ |
| `adapters/parsers/csv_parser.py` | `CsvParser` | CSV 파서 구현체 (stdlib csv로 교체 필요) |
| `adapters/parsers/pptx_parser.py` | `PptxParser` | PowerPoint 파서 구현체 ✅ |
| `adapters/parsers/hwp_parser.py` | `HwpParser` | HWP 파서 구현체 ✅ |
| `adapters/parsers/hwpx_parser.py` | `HwpxParser` | HWPX 파서 구현체 (lxml로 교체 필요) |
| `adapters/parsers/markdown_parser.py` | `MarkdownParser` | Markdown 파서 구현체 |
| `adapters/persistence/postgres_document_repo.py` | `PostgresDocumentRepository` | DocumentRepositoryPort 구현체 |
| `adapters/config/yaml_config_loader.py` | `YamlConfigLoader` | ConfigLoaderPort 구현체 |

---

### 반드시 사용해야 하는 클래스 (common-schemas에서 import)

```python
from common_schemas.document import (
    BBox,          # 좌표 정보 (x1, y1, x2, y2)
    SheetMeta,     # 엑셀 시트 정보
    SourceRef,     # 블록/청크 출처 추적
    FileMeta,      # 파일 메타데이터
    ParserMeta,    # 파서 메타데이터 (REQ-012 SSOT)
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

doc_parser/domain/
  └── entities/  ← Chunk, ChunkingStrategy, WarningInfo, ElapsedDetail
                    QualityGateResult, QualityMetrics, QualityConfig
                    PIIMaskRule
  └── ports/     ← ParserPort, DocumentRepositoryPort, ConfigLoaderPort (ABC)
  └── services/  ← NormalizationService, ChunkingService, QualityGate,
                    PIIMaskingService, ParserFactory
```

> **domain/ 레이어 import 금지 목록**
> - `pdfplumber`, `python-docx`, `openpyxl` 등 파서 라이브러리 ❌
> - `sqlalchemy`, `fastapi`, `celery` 등 프레임워크 ❌
> - `modules/*/adapters/` 방향 import ❌
> - 순수 Python + Pydantic v2 + common_schemas만 ✅
> - `ParserFactory` 는 `ParserPort(ABC)` 만 참조하므로 domain/services/ 배치 허용 ✅

---

## 4. 파일 구조

```
modules/doc-parser/
├── __init__.py
├── pyproject.toml                         ← ✅ 완료
├── config/
│   └── parser_quality.yaml                ← ✅ 완료
├── domain/
│   ├── __init__.py                        ← ✅ 완료 (수정 필요 — 신규 export 추가)
│   ├── entities/
│   │   ├── __init__.py                    ← ✅ 완료 (수정 필요)
│   │   ├── chunk.py                       ← ✅ 완료 (ChunkingStrategy 추가 필요)
│   │   ├── warning.py                     ← ✅ 완료
│   │   ├── quality.py                     ← 🔜 신규 (QualityGateResult, QualityMetrics, QualityConfig)
│   │   └── pii.py                         ← 🔜 신규 (PIIMaskRule)
│   ├── ports/
│   │   ├── __init__.py                    ← ✅ 완료 (수정 필요)
│   │   ├── parser_port.py                 ← ✅ 완료
│   │   ├── repository_port.py             ← 🔜 신규 (DocumentRepositoryPort)
│   │   └── config_port.py                 ← 🔜 신규 (ConfigLoaderPort)
│   └── services/
│       ├── __init__.py                    ← ✅ 완료 (수정 필요)
│       ├── normalizer.py                  ← ✅ 완료 (NormalizationService 로 rename 필요)
│       ├── chunking_service.py            ← ✅ 완료
│       ├── quality_gate.py                ← ✅ 완료
│       ├── pii_masking_service.py         ← ✅ 완료
│       └── parser_factory.py              ← 🔜 이동 (adapters/ → domain/services/)
├── application/
│   └── use_cases/
│       ├── __init__.py                    ← ✅ 완료 (수정 필요)
│       ├── parse_document.py              ← ✅ 완료
│       ├── extract_chunks.py              ← ✅ 완료
│       └── parsing_pipeline.py            ← 🔜 신규 (ParsingPipeline)
├── adapters/
│   ├── parsers/
│   │   ├── __init__.py                    ← ✅ 완료 (parser_factory 제거 필요)
│   │   ├── pdf_parser.py                  ← ✅ 완료
│   │   ├── docx_parser.py                 ← ✅ 완료
│   │   ├── xlsx_parser.py                 ← ✅ 완료
│   │   ├── csv_parser.py                  ← ⚠️ 완료 (pandas → stdlib csv 교체 필요)
│   │   ├── pptx_parser.py                 ← ✅ 완료
│   │   ├── hwp_parser.py                  ← ✅ 완료
│   │   ├── hwpx_parser.py                 ← ⚠️ 완료 (xml.etree → lxml 교체 필요)
│   │   └── markdown_parser.py             ← 🔜 신규
│   ├── persistence/
│   │   ├── __init__.py                    ← 🔜 신규
│   │   └── postgres_document_repo.py      ← 🔜 신규 (REQ-001 DB 스키마 확정 후)
│   └── config/
│       ├── __init__.py                    ← 🔜 신규
│       └── yaml_config_loader.py          ← 🔜 신규
└── tests/
    ├── conftest.py                        ← ✅ 완료 (수정 필요 — 신규 stub 반영)
    ├── unit/
    │   ├── domain/                        ← ✅ 완료 (51 passed, 수정 필요)
    │   └── application/                   ← 🔜 미구현
    └── integration/
        └── adapters/                      ← 🔜 미구현
```

> **⚠️ value_objects/ 폴더 제거**
> 명세서 기준 `value_objects/` 폴더 없음 → `entities/` 안으로 통합
> `QualityMetrics`, `QualityGateResult` → `entities/quality.py` 로 이동

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

### 5-2. doc_parser Port → Adapter 매핑

| Port (ABC) 정의 위치 | Adapter 구현 위치 |
|--------------------|----------------|
| `domain/ports/ParserPort` | `adapters/parsers/` |
| `domain/ports/DocumentRepositoryPort` | `adapters/persistence/` |
| `domain/ports/ConfigLoaderPort` | `adapters/config/` |

### 5-3. 절대 금지 import 패턴

```python
# ❌ domain에서 파서 라이브러리 import
from pdfplumber import ...     # adapters/에서만 허용
from docx import ...           # adapters/에서만 허용
from openpyxl import ...       # adapters/에서만 허용
from lxml import ...           # adapters/에서만 허용

# ❌ domain/application에서 프레임워크 import
from fastapi import ...        # api-server에서만 허용
from sqlalchemy import ...     # storage에서만 허용

# ❌ application에서 구체 Adapter 직접 import
from doc_parser.adapters.parsers.pdf_parser import PdfParser  # Port ABC만 참조
```

### 5-4. 새 코드 작성 절차

1. **README 읽기** — `modules/doc_parser/README.md` 먼저 확인
2. **의존성 확인** — 위 의존성 방향 규칙에 따라 import 가능 여부 확인
3. **레이어 배치** — `domain` / `application` / `adapters` 중 어디인지 판단
4. **공유 타입 사용** — 엔티티/VO는 반드시 `common_schemas`에서 import
5. **Port 분리** — 인터페이스는 `domain/ports/`, 구현은 `adapters/`
6. **보안 점검** — 하드코딩 금지, 임계값은 `config/parser_quality.yaml`에서 읽기

### 5-5. 컨벤션

- Python >= 3.11, Ruff lint (`line-length=120`)
- 타입 힌트 필수 (모든 함수 시그니처)
- ID 필드: `UUID` 타입 사용
- VO(Value Object): `frozen=True` 필수
- 환경 변수: 하드코딩 금지, `os.getenv()` 사용
- 임계값: 코드 내 숫자 직접 기입 금지 → `config/parser_quality.yaml`에서 읽기

---

## 6. entities/ 상세 설계

### 6-1. warning.py ✅

```python
class WarningInfo(BaseModel):
    code: str
    message: str
    detail: Optional[dict] = None

class ElapsedDetail(BaseModel):
    parse_ms: int = 0
    normalize_ms: int = 0
    masking_ms: int = 0
    chunking_ms: int = 0
    quality_gate_ms: int = 0
```

### 6-2. chunk.py ✅ (ChunkingStrategy 추가 필요)

```python
class ChunkOverlapMeta(BaseModel):
    has_overlap: bool
    overlap_tokens: Optional[int] = None

class Chunk(BaseModel):
    chunk_id: UUID
    chunk_type: Literal["structural", "page", "token", "table"]
    content: str
    token_count: int
    source_ref: SourceRef
    overlap_meta: Optional[ChunkOverlapMeta] = None
    block_ids: list[UUID]
    importance_score: Optional[float] = None  # REQ-004 담당

# 신규 추가
class ChunkingStrategy(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_tokens: int
    overlap_tokens: int
    token_estimator_mode: Literal["tiktoken", "char_estimate"]
```

### 6-3. quality.py 🔜 신규 (value_objects/quality.py 에서 이동 + QualityConfig 추가)

```python
class QualityMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)
    korean_ratio: float
    broken_char_ratio: float
    blocks_per_page: float
    heading_ratio: float
    valid_table_ratio: float
    structural_chunk_ratio: float
    total_chunks: int
    avg_tokens: float

class QualityGateResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    quality_status: Literal["success", "warning", "manual_correction_required", "failed"]
    metrics: QualityMetrics
    warnings: list[str]
    error_codes: list[str]
    decision_reason: str

# 신규 추가
class QualityConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    min_text_length: int
    min_text_per_page: int
    korean_ratio_warn: float
    broken_char_warn: float
    blocks_per_page_warn: float
    max_parser_warnings: int
    min_heading_ratio: float
    min_valid_table_ratio: float
    min_structural_chunk_ratio: float
    warn_threshold_count: int
```

### 6-4. pii.py 🔜 신규

```python
class PIIMaskRule(BaseModel):
    pattern: str       # 정규식 패턴
    replacement: str   # 대체 문자열
    label: str         # 마스킹 항목명 (rrn, phone 등)
```

---

## 7. ports/ 상세 설계

### 7-1. parser_port.py ✅

```python
class ParserPort(ABC):
    @abstractmethod
    def parse(self, file_path: str, file_meta: FileMeta) -> DocumentBlock: ...
    @abstractmethod
    def supports(self, mime_type: str) -> bool: ...
```

### 7-2. repository_port.py 🔜 신규

```python
class DocumentRepositoryPort(ABC):
    @abstractmethod
    def save(self, document: DocumentBlock) -> UUID: ...
    @abstractmethod
    def save_chunks(self, chunks: list[Chunk]) -> None: ...
    @abstractmethod
    def save_quality_log(self, result: QualityGateResult, document_id: UUID) -> None: ...
```

### 7-3. config_port.py 🔜 신규

```python
class ConfigLoaderPort(ABC):
    @abstractmethod
    def load_quality_config(self) -> QualityConfig: ...
    @abstractmethod
    def load_chunking_strategy(self) -> ChunkingStrategy: ...
    @abstractmethod
    def load_pii_rules(self) -> list[PIIMaskRule]: ...
```

---

## 8. services/ 상세 설계

### 8-1. normalizer.py ✅ (NormalizationService 로 rename 필요)

```python
class NormalizationService:
    def normalize(self, blocks: list[ContentBlock]) -> list[ContentBlock]: ...
    def normalize_document(self, doc: DocumentBlock) -> DocumentBlock: ...
    def normalize_block(self, block: ContentBlock) -> ContentBlock: ...
    def preprocess_hwp_text(self, text: str) -> str: ...
```

### 8-2. chunking_service.py ✅

```python
class ChunkingService:
    def chunk(self, document: DocumentBlock, strategy: ChunkingStrategy) -> list[Chunk]: ...
```

### 8-3. quality_gate.py ✅

```python
class QualityGate:
    def evaluate(self, document: DocumentBlock, config: QualityConfig) -> QualityGateResult: ...
```

### 8-4. pii_masking_service.py ✅

```python
class PIIMaskingService:
    def mask(self, blocks: list[ContentBlock], rules: list[PIIMaskRule]) -> list[ContentBlock]: ...
```

### 8-5. parser_factory.py 🔜 이동 (adapters/ → domain/services/)

```python
class ParserFactory:
    def register(self, parser: ParserPort) -> None: ...
    def get(self, mime_type: str) -> ParserPort: ...  # 없으면 ValueError(E0201)
```

---

## 9. adapters/ 상세 설계

### 9-1. 파서 라이브러리 확정 (명세서 기준)

| 파서 | 라이브러리 | 비고 |
|------|----------|------|
| `PdfParser` | `PyMuPDF(fitz)` + `pdfplumber` | 본문: fitz, 표: pdfplumber |
| `DocxParser` | `python-docx` | 서식 보존 제외 |
| `XlsxParser` | `openpyxl` | `read_only=True` 모드 |
| `CsvParser` | stdlib `csv` | ⚠️ pandas → csv 교체 필요 |
| `PptxParser` | `python-pptx` | 이미지 내 텍스트 제외 |
| `HwpParser` | `pyhwp / hwp5txt` | 표·서식·각주 제한 |
| `HwpxParser` | `lxml` | ⚠️ xml.etree → lxml 교체 필요 |
| `MarkdownParser` | `markdown-it-py` | 🔜 신규 |

### 9-2. PdfParser 특이사항

```python
class PdfParser(ParserPort):
    def is_scanned_pdf(self, file_path: str) -> bool:
        # PyMuPDF로 첫 3페이지 텍스트 추출
        # 평균 텍스트 길이 임계값 미만 → True (E0212)
        ...
```

### 9-3. persistence/ 🔜 신규 (REQ-001 DB 스키마 확정 후)

```python
class PostgresDocumentRepository(DocumentRepositoryPort):
    # parsed_documents, document_chunks, parser_logs, quality_gate_logs 연동
    ...
```

### 9-4. config/ 🔜 신규

```python
class YamlConfigLoader(ConfigLoaderPort):
    # config/parser_quality.yaml 에서 QualityConfig, ChunkingStrategy, PIIMaskRule 로드
    ...
```

---

## 10. 구현 순서

```
✅ Step 1:  domain/entities/warning.py
✅ Step 2:  domain/entities/chunk.py
✅ Step 3:  domain/entities/__init__.py
✅ Step 4:  domain/value_objects/quality.py        (→ entities/quality.py 로 이동 예정)
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
✅ Step 17: domain/services/normalizer.py          (NormalizationService rename 필요)
✅ Step 18: adapters/parsers/parser_factory.py     (→ domain/services/ 로 이동 필요)
✅ Step 19: adapters/parsers/pdf_parser.py
✅ Step 20: adapters/parsers/docx_parser.py
✅ Step 21: adapters/parsers/xlsx_parser.py
⚠️ Step 22: adapters/parsers/csv_parser.py        (pandas → stdlib csv 교체 필요)
✅ Step 23: adapters/parsers/pptx_parser.py
✅ Step 24: adapters/parsers/hwp_parser.py
⚠️ Step 25: adapters/parsers/hwpx_parser.py       (xml.etree → lxml 교체 필요)
✅ Step 26: adapters/parsers/__init__.py

🔜 Step 27: domain/entities/quality.py            (value_objects/ → entities/ 이동)
🔜 Step 28: domain/entities/pii.py                (PIIMaskRule 신규)
🔜 Step 29: domain/entities/chunk.py 수정          (ChunkingStrategy 추가)
🔜 Step 30: domain/ports/repository_port.py       (DocumentRepositoryPort 신규)
🔜 Step 31: domain/ports/config_port.py           (ConfigLoaderPort 신규)
🔜 Step 32: domain/services/parser_factory.py     (adapters/ → domain/services/ 이동)
🔜 Step 33: application/use_cases/parsing_pipeline.py  (ParsingPipeline 신규)
🔜 Step 34: adapters/parsers/markdown_parser.py   (MarkdownParser 신규)
🔜 Step 35: adapters/config/yaml_config_loader.py (YamlConfigLoader 신규)
🔜 Step 36: adapters/persistence/postgres_document_repo.py (REQ-001 확정 후)
```

---

## 11. 테스트 계획

```
tests/
├── conftest.py                    ← ✅ 완료 (수정 필요 — 신규 stub 반영)
├── unit/
│   ├── domain/                    ← ✅ 완료 (51 passed, 수정 필요)
│   │   ├── test_chunk.py
│   │   ├── test_quality.py
│   │   ├── test_pii_masking.py
│   │   ├── test_chunking_service.py
│   │   └── test_quality_gate.py
│   └── application/               ← 🔜 미구현
└── integration/
    └── adapters/                  ← 🔜 미구현
```

| 테스트 대상 | 주요 케이스 |
|------------|------------|
| `Chunk` | UUID 자동생성, importance_score=None 기본값 |
| `QualityGateResult` | status 4종, warning 누적 → manual_correction_required 격상 |
| `PIIMaskingService` | RRN/전화/이메일/계좌/카드 마스킹, allow-list |
| `ChunkingService` | 4가지 전략 우선순위 |
| `QualityGate` | yaml 설정값 기반 판단 |
| `PdfParser` | 스캔 PDF 감지 → E0212, 정상 PDF 파싱 |
| `ParseDocumentUseCase` | 파서 선택, 정규화, PII 마스킹, 품질 검증 흐름 |
| `ExtractChunksUseCase` | 청킹 결과, importance_score=None |
| `ParsingPipeline` | 전체 파이프라인 end-to-end |

---

## 12. 미확정 항목

| 항목 | 내용 | 협의 대상 |
|------|------|----------|
| `ChunkingService` 토큰 계산 | 폐쇄망 tiktoken 불가 시 `char × 0.7` 전환 | config/parser_quality.yaml |
| PII Allow-list 패턴 | 하네스 엔지니어링 일련번호 오검출 방지 | 황대원님 협의 필요 |
| `importance_score` 계산 시점 | REQ-004 AI_Agent 담당 확인 완료 ✅ | 신정혜님 확인됨 |
| `HandoffPayload` 구조 | AI_Agent로 넘기는 데이터 필드 정의 | 황대원님 (REQ-012 SSOT) |
| `HWPX` POC 검증 | lxml 기반 실제 동작 확인 필요 | 내부 |
| `Normalizer` 메서드 목록 | v2.3 기준 나머지 메서드 확정 필요 | 내부 |
| `PostgresDocumentRepository` | REQ-001 DB 스키마 확정 후 구현 | 황대원님 (REQ-001) |