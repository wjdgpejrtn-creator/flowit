# REQ-006 Doc-Parser -- 구현 명세

> 담당: 김진형
> 모듈 경로: `modules/doc_parser/`
> 의존 패키지: `common_schemas >= 0.1.0`

---

## common_schemas에서 import할 클래스

자체적으로 DocumentBlock, FileMeta, Block, SourceRef 등을 재정의하지 않는다. 모두 REQ-012에서 import한다.

| 클래스 | 소스 모듈 | 용도 |
|--------|-----------|------|
| `DocumentBlock` | `common_schemas.document` | 파싱 최종 결과 엔티티. 파서 출력의 루트 객체. **분석 lifecycle 3필드 포함**(`analysis_status` `AnalysisStatus`, `analysis_error` `Optional[str]`, `analyzed_at` `Optional[UtcDatetime]` — REQ-009 polling 신호, PR #218) |
| `AnalysisStatus` | `common_schemas.enums` | 분석 lifecycle enum (`pending`/`running`/`completed`/`failed`) — Celery worker가 갱신, api_server가 응답에 노출 (PR #218) |
| `ContentBlock` | `common_schemas.document` | 문서 내 개별 블록 (text/table/image/heading/code) |
| `FileMeta` | `common_schemas.document` | 파일 메타정보 (file_name, file_type, mime_type, file_size 등) |
| `ParserMeta` | `common_schemas.document` | 파서 이름/버전/실행시간 메타 |
| `SourceRef` | `common_schemas.document` | 블록의 출처 참조 (page, section, bbox, sheet_name 등) |
| `BBox` | `common_schemas.document` | 블록 위치 좌표 (x1, y1, x2, y2) |
| `SheetMeta` | `common_schemas.document` | Excel 시트 메타정보 (sheet_name, row_count, col_count) |
| `Chunk` | `common_schemas.document` | 청킹 결과 엔티티 (SSOT 승격 확정, PR #34) |
| `ChunkingStrategy` | `common_schemas.document` | 청킹 전략 설정 VO (SSOT 승격 확정, PR #34) |
| `QualityGateResult` | `common_schemas.document` | 파서 품질 게이트 판정 결과 (SSOT 승격 확정, PR #34) |
| `QualityMetrics` | `common_schemas.document` | 파서 출력 품질 수치 메트릭 (SSOT 승격 확정, PR #34) |
| `WarningInfo` | `common_schemas.document` | 파싱 경고 정보 (SSOT 승격 확정, PR #34) |
| `ParseCoverage` | `common_schemas.document` | 파싱 커버리지 지표 (`QualityGateResult.coverage` 타입 — PR #34 결정 누락분, REQ-012 이관) |

### import 예시

```python
from common_schemas import (
    DocumentBlock,
    ContentBlock,
    FileMeta,
    ParserMeta,
    SourceRef,
    BBox,
    SheetMeta,
    Chunk,
    ChunkingStrategy,
    QualityGateResult,
    QualityMetrics,
    ParseCoverage,
    WarningInfo,
)
```

---

## 이 모듈에서 구현할 클래스

### Domain Layer (`domain/`)

#### domain/entities

| 클래스 | 필드 | 설명 |
|--------|------|------|
| `QualityConfig` | `min_text_length: int`, `min_text_per_page: int`, `korean_ratio_warn: float`, `broken_char_warn: float`, `blocks_per_page_warn: float`, `max_parser_warnings: int`, `min_heading_ratio: float`, `min_valid_table_ratio: float`, `min_structural_chunk_ratio: float`, `warn_threshold_count: int` | `config/parser_quality.yaml`에서 로드하는 설정 VO (모듈 내부 유지) |
| `PIIMaskRule` | `pattern: str`, `replacement: str`, `label: str` | PII 마스킹 규칙 정의 (모듈 내부 유지) |
| `ElapsedDetail` | `parse_ms: float`, `normalize_ms: float`, `pii_ms: float`, `chunk_ms: float`, `quality_ms: float` | 파이프라인 단계별 처리 시간 (모듈 내부 유지) |
| `VisionType` | `TABLE`, `GRAPH`, `CHART`, `CORRUPTED` | 비전 추출 유형 enum. TableDetector가 감지한 상황에 따라 Gemma4 프롬프트 결정 |

> **SSOT 주의**: `Chunk`, `ChunkingStrategy`, `QualityGateResult`, `QualityMetrics`, `ParseCoverage`, `WarningInfo`는 `common_schemas/document.py` SSOT다 (PR #34 결정 → REQ-012 common_schemas 0.11.0에서 실제 이관 완료). `domain/entities/{chunk,quality,warning}.py`는 하위호환 shim — 기존 import 경로는 유지되나 신규 코드는 `common_schemas`에서 직접 import. 모듈 내 재정의 금지.

#### domain/services

| 서비스 클래스 | 메서드 | 설명 |
|-------------|--------|------|
| `ChunkingService` | `chunk(document: DocumentBlock, strategy: Optional[ChunkingStrategy] = None) -> list[Chunk]` | 문서를 의미 단위로 분할. 4단계 우선순위(구조적/물리적/토큰/표 특수처리) 적용 |
| `QualityGate` | `evaluate(document: DocumentBlock, chunks: list[Chunk]) -> QualityGateResult` | 파싱 품질 검증. 임계값은 `config/parser_quality.yaml`에서 로드 |
| `PIIMaskingService` | `mask_document(document: DocumentBlock) -> tuple[DocumentBlock, list[WarningInfo]]` | PII 단방향 마스킹. 정규화 이후/청킹 이전 수행 |
| `NormalizationService` | `normalize_document(document: DocumentBlock) -> DocumentBlock` | 기본 텍스트 정규화 (공백/특수문자/인코딩 정리) |

#### domain/ports (ABC 인터페이스)

| 포트 | 메서드 | 구현 위치 |
|------|--------|----------|
| `ParserPort` | `parse(file_path: str, file_meta: FileMeta) -> DocumentBlock` | `adapters/parsers/` |
| | `supports(mime_type: str) -> bool` | |
| `VisionPort` | `extract(file_path: str, vision_type: VisionType, page_num: int, block_index: int) -> ContentBlock \| None` | `adapters/vision/` |
| `DocumentRepositoryPort` | `save(document: DocumentBlock) -> UUID` | `modules/storage/repositories/pg_document_repository.py` (REQ-008 storage). upload(blocks=[]) → analyze(parsed) UPSERT(merge) (PR #197) |
| | `save_chunks(chunks: list[Chunk]) -> None` | |
| | `save_quality_log(result: QualityGateResult, document_id: UUID) -> None` | |
| | `get_by_id(document_id: UUID) -> DocumentBlock \| None` | `GET /api/v1/documents/{id}` + worker analyze가 메타 조회에 사용. 인가는 호출자(`PermissionSource.user_id` 비교) 책임 (PR #197, 조장 — Update/Delete 동일 패턴으로 owner-검사 라우터 분산 방지) |
| | `delete(document_id: UUID) -> bool` | `DELETE /api/v1/documents/{id}` (응답 204/404/403)가 사용. hard delete — GCS 원본 + 자식(document_chunks/quality_gate_logs) 명시 제거 후 부모 row 삭제(DDL CASCADE 비의존, GCS는 NotFoundError swallow로 멱등). 성공 True/미존재 False. 인가는 호출자(owner 비교) 책임 |
| `ConfigLoaderPort` | `load_quality_config() -> QualityConfig` | `adapters/config/` |
| | `load_chunking_strategy() -> ChunkingStrategy` | |
| | `load_pii_rules() -> list[PIIMaskRule]` | |

### Application Layer (`application/`)

| 유스케이스 | Input -> Output | 설명 |
|-----------|----------------|------|
| `ParseDocumentUseCase` | `(file_path: str, file_meta: FileMeta) -> DocumentBlock` | 파서 선택 -> 파싱 -> 정규화 -> PII 마스킹 -> 품질 게이트 판정 |
| `ExtractChunksUseCase` | `(document: DocumentBlock) -> list[Chunk]` | 청킹 전략 로드 -> 청킹 -> Chunk 리스트 반환 |
| `ParsingPipeline` | `(file_path: str, file_meta: FileMeta) -> tuple[DocumentBlock, list[Chunk], QualityGateResult]` | 전체 파이프라인 오케스트레이션: 파서 선택 -> 파싱 -> 정규화 -> PII 마스킹 -> QualityGate -> Chunk 생성 -> 저장 |

### Infrastructure/Adapter Layer (`adapters/`)

#### adapters/parsers -- 8종 파서 구현체

| 파서 클래스 | 지원 MIME 타입 | 주요 라이브러리 |
|------------|--------------|----------------|
| `PdfParser` | `application/pdf` | `pdfplumber`, `pymupdf` |
| `DocxParser` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `python-docx` |
| `XlsxParser` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `openpyxl` |
| `CsvParser` | `text/csv` | `csv` (stdlib) |
| `PptxParser` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | `python-pptx` |
| `HwpParser` | `application/x-hwp` | `pyhwp` / 외부 CLI |
| `HwpxParser` | `application/hwp+zip` | XML 파싱 (`lxml`) |
| `MarkdownParser` | `text/markdown` | `markdown-it-py` |

> 모든 파서는 `ParserPort`를 구현하며, `ParserFactory`에 자동 등록된다.

#### adapters/persistence

| 클래스 | 설명 |
|--------|------|
| `PostgresDocumentRepository` | `DocumentRepositoryPort` 구현. `parsed_documents`, `document_chunks`, `parser_logs`, `quality_gate_logs` 테이블 연동 |

#### adapters/config

| 클래스 | 설명 |
|--------|------|
| `YamlConfigLoader` | `ConfigLoaderPort` 구현. `config/parser_quality.yaml`에서 설정 로드 |

#### adapters/vision

| 클래스 | 설명 |
|--------|------|
| `VisionExtractor` | `VisionPort` 구현. fitz(PyMuPDF)로 페이지 캡처 → Gemma4(Modal) 비전 분석. LibreOffice 미사용 |
| `TableDetector` | 블록 스트림에서 비전 트리거 감지. block_type + broken_char_ratio 기준으로 TABLE/GRAPH/CHART/CORRUPTED 판단 |
| `VisionPromptStrategy` | VisionType별 Gemma4 프롬프트 정책. 정책 변경이 잦아 domain이 아닌 adapters에 위치 |

#### adapters (루트)

| 클래스 | 설명 |
|--------|------|
| `InterleavingParser` | `ParserPort` 구현. 텍스트 파싱 + 비전 인터리빙 지휘자. CSV/MD는 비전 스킵, 나머지는 `_parse_interleaving()` 단일 경로로 통일 |
| `ParserFactory` | MIME 타입 기반 파서 선택 팩토리. 순환 import 방지를 위해 `domain/services`가 아닌 `adapters`에 위치. `from_yaml(config_path)` 클래스 메서드로 yaml 설정 주입 |

---

## 합의된 변경사항 (클래스 다이어그램 교차분석)

| 항목 | 변경 내용 | 근거 |
|------|----------|------|
| 자체 DocumentBlock/FileMeta/Block/SourceRef 삭제 | REQ-012 common_schemas SSOT 원칙. 중복 정의 전면 제거 | HIGH-001 교차분석 결과 |
| `QualityGateResult` 신규 정의 | `AnalysisResult`(REQ-012)와는 목적이 다름 (파서 QC vs LLM 분석). 별도 타입으로 확정 | HIGH-005 논의 결정 |
| `QualityMetrics` 신규 정의 | QualityGateResult 내부에서 사용하는 수치 메트릭 VO | HIGH-005 |
| `Chunk.importance_score` Optional | REQ-004 IntentAnalyzer가 나중에 채우는 필드. 파서 시점에는 None | MEDIUM-003 |
| `mime_type` FileMeta에 포함 확인 | REQ-012 FileMeta 정의에 `mime_type: str` 이미 포함됨. 추가 작업 불필요 | LOW-002 확인 완료 |
| `ParserMeta` common_schemas import | 파서 메타데이터도 SSOT에서 가져옴. 자체 정의 불필요 | HIGH-001 |

---

## 의존성 관계

```
modules/doc_parser
├── depends on ─────────────────────────────────────────────────────────────
│   ├── packages/common_schemas   (DocumentBlock, ContentBlock, FileMeta, ParserMeta, SourceRef, BBox, SheetMeta)
│   └── modules/storage           (DocumentRepository가 파싱 결과 영속화 — REQ-001)
│
├── depended by ────────────────────────────────────────────────────────────
│   ├── modules/ai_agent — Workflow Composer (REQ-004: 문서 기반 워크플로우 생성 시 청크 조회)
│   ├── modules/ai_agent — Skills Builder   (REQ-004: BuildFromSOPUseCase가 DocumentBlock 소비
│   │                                        → SkillNode 추출 → NodeDefinitionRepository.upsert)
│   ├── services/api_server       (문서 업로드 엔드포인트에서 ParseDocumentUseCase 호출)
│   └── services/execution_engine (워크플로우 노드로 파서 호출 시)
│
└── runtime dependencies ───────────────────────────────────────────────────
    ├── PostgreSQL                 (parsed_documents, document_chunks 저장)
    └── config/parser_quality.yaml (품질 게이트 임계값)
```

### 패키지 설치 의존성 (pyproject.toml)

```toml
[project]
dependencies = [
    "common_schemas",
    "pydantic>=2.0",
    "pdfplumber>=0.10",
    "pymupdf>=1.23",
    "python-docx>=1.0",
    "openpyxl>=3.1",
    "python-pptx>=0.6",
    "lxml>=5.0",
    "pyyaml>=6.0",
]
```

---

## 디렉토리 구조 (목표)

```
modules/doc_parser/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── chunk.py              ← Chunk, ChunkingStrategy (common_schemas SSOT import 후 re-export)
│   │   ├── quality.py            ← QualityGateResult, QualityMetrics (SSOT), QualityConfig (내부)
│   │   ├── warning.py            ← WarningInfo (SSOT), ElapsedDetail (내부)
│   │   ├── pii.py                ← PIIMaskRule
│   │   └── vision_type.py        ← VisionType enum (TABLE/GRAPH/CHART/CORRUPTED)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chunking_service.py   ← ChunkingService
│   │   ├── quality_gate.py       ← QualityGate
│   │   ├── pii_masking.py        ← PIIMaskingService
│   │   └── normalization.py      ← NormalizationService
│   └── ports/
│       ├── __init__.py
│       ├── parser_port.py        ← ParserPort (ABC)
│       ├── vision_port.py        ← VisionPort (ABC)
│       ├── repository_port.py    ← DocumentRepositoryPort (ABC)
│       └── config_port.py        ← ConfigLoaderPort (ABC)
├── application/
│   ├── __init__.py
│   └── use_cases/
│       ├── __init__.py
│       ├── parse_document.py     ← ParseDocumentUseCase
│       ├── extract_chunks.py     ← ExtractChunksUseCase
│       └── parsing_pipeline.py   ← ParsingPipeline
├── adapters/
│   ├── __init__.py
│   ├── interleaving_parser.py    ← InterleavingParser (텍스트+비전 인터리빙 지휘자)
│   ├── parser_factory.py         ← ParserFactory (순환 import 방지로 adapters에 위치)
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py
│   │   ├── docx_parser.py
│   │   ├── xlsx_parser.py
│   │   ├── csv_parser.py
│   │   ├── pptx_parser.py
│   │   ├── hwp_parser.py
│   │   ├── hwpx_parser.py
│   │   └── markdown_parser.py
│   ├── vision/
│   │   ├── __init__.py
│   │   ├── vision_extractor.py   ← VisionExtractor (fitz+Gemma4)
│   │   ├── table_detector.py     ← TableDetector (비전 트리거 감지)
│   │   └── prompts.py            ← VisionPromptStrategy (Gemma4 프롬프트 정책)
│   ├── persistence/
│   │   ├── __init__.py
│   │   └── postgres_document_repo.py
│   └── config/
│       ├── __init__.py
│       └── yaml_config_loader.py
├── config/
│   └── parser_quality.yaml       ← 품질 게이트 임계값 설정
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── domain/
    │   └── application/
    └── integration/
        └── adapters/
```

---

## 구현 우선순위

| 순서 | 대상 | 이유 |
|------|------|------|
| 1 | `domain/entities/` (Chunk, QualityGateResult, QualityMetrics) | 다른 레이어가 모두 참조 |
| 2 | `domain/ports/` (ParserPort, DocumentRepositoryPort) | 인터페이스 확정 후 병렬 구현 가능 |
| 3 | `domain/services/` (ChunkingService, QualityGate, PIIMaskingService) | 비즈니스 로직 핵심 |
| 4 | `application/use_cases/` (ParsingPipeline) | 서비스 조합 오케스트레이션 |
| 5 | `adapters/parsers/` (PdfParser 먼저, 이후 나머지) | 외부 라이브러리 의존 |
| 6 | `adapters/persistence/` | REQ-001 DB 스키마 확정 후 구현 |
