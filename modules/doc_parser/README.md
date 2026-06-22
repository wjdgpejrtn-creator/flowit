# doc_parser

> REQ-006: 8종 문서 파서, 청킹, PII 마스킹, 품질 게이트
>
> 구현 명세 → [`docs/specs/REQ-006-doc_parser.md`](../../docs/specs/REQ-006-doc_parser.md)

## 설치

```bash
pip install -e modules/doc_parser
pip install -e "modules/doc_parser[dev]"
```

## Quick Start

```python
from common_schemas import Chunk, QualityGateResult, QualityMetrics  # REQ-012 SSOT (0.11.0)
from doc_parser.domain.services import (
    ChunkingService, QualityGate, PIIMaskingService, NormalizationService,
)
from doc_parser.adapters.parser_factory import ParserFactory
from doc_parser.domain.ports import ParserPort, DocumentRepositoryPort, ConfigLoaderPort
from doc_parser.application.use_cases import (
    ParseDocumentUseCase, ExtractChunksUseCase, ParsingPipeline,
)
```

## common_schemas에서 import하는 타입

| 클래스 | import 경로 | 용도 |
|--------|-------------|------|
| `DocumentBlock` | `common_schemas.document` | 파싱 최종 결과 엔티티 (루트) |
| `ContentBlock` | `common_schemas.document` | 문서 내 개별 블록 (text/table/image/heading/code) |
| `FileMeta` | `common_schemas.document` | 파일 메타정보 |
| `ParserMeta` | `common_schemas.document` | 파서 이름/버전/실행시간 메타 |
| `SourceRef` | `common_schemas.document` | 블록 출처 참조 (page, section, bbox 등) |
| `BBox` | `common_schemas.document` | 블록 위치 좌표 (x1, y1, x2, y2) |
| `SheetMeta` | `common_schemas.document` | Excel 시트 메타 (sheet_name, row_count, col_count) |

## Public API

### domain/entities

> `Chunk`, `QualityGateResult`, `QualityMetrics` 는 `common_schemas` SSOT (0.11.0). `from common_schemas import ...` 로 직접 import 권장.

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `Chunk` | `block: ContentBlock`, `importance_score: Optional[float]`, `embedding: Optional[list[float]]`, `chunk_index: int`, `parent_document_id: UUID` | 청킹 결과. `importance_score`는 REQ-004 IntentAnalyzer가 나중에 채움 |
| `QualityGateResult` | `quality_status: Literal["success","warning","manual_correction_required","failed"]`, `metrics: QualityMetrics`, `warnings: list[WarningInfo]`, `error_codes: list[str]`, `decision_reason: str`, `coverage: ParseCoverage` | 파서 품질 게이트 판정 결과 |
| `QualityMetrics` | `korean_ratio: float`, `broken_char_ratio: float`, `blocks_per_page: float`, `heading_ratio: float`, `valid_table_ratio: float`, `structural_chunk_ratio: float`, `total_chunks: int`, `avg_tokens: float` | 품질 수치 메트릭 |

### domain/entities — Value Objects

| 클래스 | 설명 |
|--------|------|
| `QualityConfig` | 품질 게이트 설정 (9개 임계값). `config/parser_quality.yaml`에서 로드 |
| `ChunkingStrategy` | 청킹 전략. `max_tokens: int`, `overlap_tokens: int`, `token_estimator_mode: Literal["tiktoken","char_estimate"]` |
| `PIIMaskRule` | PII 마스킹 규칙. `pattern: str`, `replacement: str`, `label: str` |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `ChunkingService` | `chunk(document: DocumentBlock, strategy: ChunkingStrategy) → list[Chunk]` | 4단계 우선순위 청킹 (구조적→물리적→토큰→표 특수처리) |
| `QualityGate` | `evaluate(document: DocumentBlock, config: QualityConfig) → QualityGateResult` | 설정 기반 품질 검증. warning 누적 시 manual_correction_required 격상 |
| `PIIMaskingService` | `mask(blocks: list[ContentBlock], rules: list[PIIMaskRule]) → list[ContentBlock]` | PII 단방향 마스킹. 정규화 이후/청킹 이전 수행 |
| `NormalizationService` | `normalize(blocks: list[ContentBlock]) → list[ContentBlock]` | 기본 텍스트 정규화 (공백/특수문자/인코딩 정리) |

### adapters/parser_factory

| 클래스 | 메서드 | 설명 |
|--------|--------|------|
| `ParserFactory` | `get(mime_type: str) → ParserPort` | MIME 타입 기반 파서 선택. 비전 모드 활성화 시 InterleavingParser 자동 래핑 |
| | `register(parser: ParserPort) → None` | 파서 등록 |

### domain/ports (인터페이스)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `ParserPort` | `parse(file_path: str, file_meta: FileMeta) → DocumentBlock` | `doc_parser/adapters/parsers/` (자체 구현) |
| | `supports(mime_type: str) → bool` | |
| `DocumentRepositoryPort` | `async save(document: DocumentBlock) → UUID` | `adapters/persistence/` (REQ-001 연동) |
| | `async save_chunks(chunks: list[Chunk]) → None` | |
| | `async save_quality_log(result: QualityGateResult, document_id: UUID) → None` | |
| `ConfigLoaderPort` | `load_quality_config() → QualityConfig` | `adapters/config/` |
| | `load_chunking_strategy() → ChunkingStrategy` | |
| | `load_pii_rules() → list[PIIMaskRule]` | |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ParseDocumentUseCase` | `file_path: str, file_meta: FileMeta → DocumentBlock` | 파서 선택 → 파싱 → 정규화 → PII 마스킹 → 품질 판정 |
| `ExtractChunksUseCase` | `document: DocumentBlock → list[Chunk]` | 청킹 전략 로드 → 청킹 → Chunk 리스트 반환 |
| `ParsingPipeline` | `file_path: str, file_meta: FileMeta → tuple[DocumentBlock, list[Chunk], QualityGateResult]` | 전체 파이프라인 오케스트레이션 (파싱→정규화→PII→QG→청킹→저장) |

### adapters/parsers — 8종 파서 구현체

| 파서 | 지원 MIME 타입 | 주요 라이브러리 |
|------|--------------|----------------|
| `PdfParser` | `application/pdf` | `pdfplumber`, `pymupdf` |
| `DocxParser` | `application/vnd.openxmlformats-...wordprocessingml.document` | `python-docx` |
| `XlsxParser` | `application/vnd.openxmlformats-...spreadsheetml.sheet` | `openpyxl` |
| `CsvParser` | `text/csv` | `csv` (stdlib) |
| `PptxParser` | `application/vnd.openxmlformats-...presentationml.presentation` | `python-pptx` |
| `HwpParser` | `application/x-hwp` | `pyhwp` / 외부 CLI |
| `HwpxParser` | `application/hwp+zip` | `lxml` |
| `MarkdownParser` | `text/markdown` | `markdown-it-py` |

## 의존 관계

```
Upstream (이 모듈이 의존):
  ├── common_schemas (REQ-012)
  │     └── DocumentBlock, ContentBlock, FileMeta, ParserMeta, SourceRef, BBox, SheetMeta
  └── storage (REQ-008) / database (REQ-001)
        └── DocumentRepositoryPort 구현체 (파싱 결과 영속화)

Downstream (이 모듈에 의존):
  ├── ai_agent (REQ-004)          → 문서 기반 워크플로우 생성 시 청크 조회
  ├── api_server (REQ-009)        → 문서 업로드 엔드포인트에서 ParseDocumentUseCase 호출
  └── execution_engine (REQ-007)  → 워크플로우 노드로 파서 호출 시
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `PARSER_MAX_FILE_SIZE_MB` | N | 최대 파일 크기 (기본: 10MB) |
| `PARSER_TIMEOUT_SECONDS` | N | 파싱 타임아웃 (기본: 120s) |
| `OCR_ENABLED` | N | OCR 활성화 여부 (기본: false) |
| `HF_TOKEN` | N | Gemma4 HuggingFace 접근 토큰 (비전 모드 활성화 시 필요) |
| `MODAL_TOKEN` | N | Modal 워크스페이스 인증 토큰 (비전 모드 활성화 시 필요) |
| `MODAL_TOKEN_SECRET` | N | Modal Secret 키 (비전 모드 활성화 시 필요) |

## 에러 코드

| 에러 코드 | 설명 | 처리 방법 |
|----------|------|----------|
| `E0201` | 지원하지 않는 파일 형식 | 지원 형식 안내 |
| `E0202` | 파일 손상 또는 읽기 실패 | 재업로드 요청 |
| `E0203` | 텍스트 추출 실패 | `failed` + 수동 입력 유도 |
| `E0204` | 표 추출 실패 | 일반: `warning` / 하네스: `manual_correction_required` |
| `E0205` | HWP 파서 제한 지원 실패 | HWPX/DOCX 변환 권고 |
| `E0208` | HWPX XML 파싱 실패 | 수동 텍스트 입력 유도 |
| `E0211` | 파서 결과 품질 부족 | `manual_correction_required` 전환 |
| `E0212` | OCR 필요 문서 감지 | MVP 제외 안내 |

## 성능 요구사항

| 처리 유형 | 목표 | 비고 |
|----------|------|------|
| TXT / CSV / 짧은 DOCX | 30초 이내 | 동기 처리 |
| 일반 PDF / DOCX / PPTX | 60초 이내 | 동기 처리 |
| HWP / HWPX | 60~120초 | 제한 지원 |
| OCR 필요 (스캔 PDF) | MVP 제외 | Phase 2 |

## 테스트

```bash
pytest modules/doc_parser/tests/
```
