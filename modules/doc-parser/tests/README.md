# doc-parser

> REQ-006: 7종 문서 파서, 청킹, 품질 게이트

## 설치

```bash
pip install -e modules/doc-parser
pip install -e "modules/doc-parser[dev]"
```

## Quick Start

```python
from doc_parser.domain.services import ChunkingService, QualityGate
from doc_parser.domain.ports import ParserPort
from doc_parser.application.use_cases import ParseDocumentUseCase, ExtractChunksUseCase
from doc_parser.adapters.parsers import PdfParser, DocxParser, XlsxParser
```

## Public API

### domain/entities

| 클래스 | 설명 |
|--------|------|
| `ParserMeta` | 파서 메타데이터 (이름, 버전, 설정) |

> 파싱 결과 엔티티(`DocumentBlock`, `ContentBlock`, `FileMeta`)는 `common-schemas`에서 import

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `ChunkingService` | `chunk(document: DocumentBlock, strategy) → list[ContentBlock]` | 문서를 의미 단위 블록으로 분할 |
| `QualityGate` | `evaluate(blocks: list[ContentBlock]) → bool` | 파싱 품질 검증 (누락/깨짐 감지) |

### domain/ports (인터페이스)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `ParserPort` | `parse(file_path, file_meta) → DocumentBlock` | `doc-parser/adapters/parsers/` (자체 구현) |
| | `supports(mime_type) → bool` | |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ParseDocumentUseCase` | `file_path, FileMeta → DocumentBlock` | 적절한 파서 선택 → 파싱 → 품질 검증 |
| `ExtractChunksUseCase` | `DocumentBlock → list[ContentBlock]` | 청킹 + importance_score 산정 |

### adapters/parsers — 7종 파서 구현체

| 파서 | 지원 확장자 | 설명 |
|------|-----------|------|
| `PdfParser` | .pdf | PDF 텍스트/레이아웃 추출 |
| `DocxParser` | .docx | Word 문서 파싱 |
| `XlsxParser` | .xlsx | Excel 시트 → 테이블 블록 변환 |
| `CsvParser` | .csv | CSV 테이블 파싱 |
| `PptxParser` | .pptx | PowerPoint 슬라이드 추출 |
| `HwpParser` | .hwp | 한글(HWP) 문서 파싱 |
| `HwpxParser` | .hwpx | 한글(HWPX 2.0) 문서 파싱 |

## 의존 관계

```
이 모듈 → common-schemas (DocumentBlock, ContentBlock, FileMeta, SourceRef, BBox, ParserMeta)
이 모듈 ← ai-agent (문서 기반 워크플로우 생성 시 청크 조회)
이 모듈 ← storage (DocumentRepository가 파싱 결과 영속화)
이 모듈 ← api-server (문서 업로드 엔드포인트에서 호출)
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `PARSER_MAX_FILE_SIZE_MB` | N | 최대 파일 크기 (기본: 10MB) |
| `PARSER_TIMEOUT_SECONDS` | N | 파싱 타임아웃 (기본: 120s) |
| `OCR_ENABLED` | N | OCR 활성화 여부 (기본: false) |

## 파서 공통 인터페이스

```python
class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> DocumentBlock: ...

    @abstractmethod
    def supports(self, file_type: str) -> bool: ...

class ParserFactory:
    _registry: list[BaseParser] = []

    @classmethod
    def get(cls, file_type: str) -> BaseParser:
        for p in cls._registry:
            if p.supports(file_type):
                return p
        raise ValueError(f'지원하지 않는 파일 유형: {file_type}')
```

## 처리 흐름

```
파일 입력
  → 입력값 검증 (REQ-002 FR-002-15)   ← 확장자·크기·MIME 타입 (최대 10MB)
  → ParserFactory.get(file_type) → 파서 실행
  → DocumentBlock JSON 변환             ← Pydantic v2 타입 보장
  → 기본 정규화
  → PII 마스킹                          ← 정규화 이후 수행
  → 청킹
  → Parser Quality Gate                 ← 설정 파일 기반 임계값
  → 결과 출력 + DB 저장 → AI_Agent 전달
```

## PII 마스킹

> PII 마스킹은 기본 정규화 이후, 청킹 이전에 수행한다. MVP는 단방향 마스킹만 지원.

| 항목 | 마스킹 패턴 | 대체 문자열 |
|------|-----------|------------|
| 주민등록번호 | `\d{6}-[1-4]\d{6}` | `[MASKED_RRN]` |
| 전화번호 | `0\d{1,2}-\d{3,4}-\d{4}` | `[MASKED_PHONE]` |
| 이메일 | `[\w.]+@[\w.]+` | `[MASKED_EMAIL]` |
| 계좌번호 | `\d{3,4}-\d{2,6}-\d{5,7}` | `[MASKED_ACCOUNT]` |
| 카드번호 | `\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}` | `[MASKED_CARD]` |

> PII Allow-list: 하네스 도면·부품 리스트의 엔지니어링 일련번호가 PII 패턴과 유사한 경우 오검출 가능. Allow-list 패턴은 별도 협의.

## 청킹 전략

| 우선순위 | 기준 | 설명 |
|---------|------|------|
| 1순위 | 구조적 분할 | `heading` 블록 기준 섹션 분리. 미감지 시 번호·기호·짧은 제목형 패턴으로 후보 탐지 |
| 2순위 | 물리적 분할 | 제목 감지 어려운 문서는 `page` 단위 우선 분할 |
| 3순위 | 토큰 최적화 | 섹션·페이지 청크 토큰 초과 시 `RecursiveCharacterTextSplitter`로 재귀 분할 (`paragraph`/`list`만) |
| 4순위 | 표 특수 처리 | `table` 타입은 독립 청크. 오버랩 없음. 초과 시 header 유지 후 row group(20행) 단위 분할 |

> 토큰 계산은 `config/parser_quality.yaml`의 `token_estimator_mode` 키로 지정. 폐쇄망에서 tiktoken 사용 불가 시 `char_estimate` (char × 0.7)로 전환.

## Parser Quality Gate

> 모든 임계값은 `config/parser_quality.yaml`에서 읽는다. 코드 내 숫자 직접 기입 금지.

### 처리 상태

| 상태 | 의미 | 후속 처리 |
|------|------|----------|
| `success` | 추출 품질 양호 | 결과 전달 |
| `warning` | 일부 구조 불확실 | 결과 전달 + 검수 표시 |
| `manual_correction_required` | 자동 해석 불안정 | 에러코드와 함께 반환 |
| `failed` | 파싱 완전 불가 | 재업로드·변환·직접 입력 요청 |

### 판단 기준

| 판단 항목 | 기준 | 판단 결과 | 설정 키 |
|----------|------|----------|---------|
| 추출 텍스트 길이 (동적) | `< max(page_count × min_text_per_page, min_text_length)` | `failed` | `min_text_length`, `min_text_per_page` |
| 한글 비율 | `< korean_ratio_warn` | `warning` | `korean_ratio_warn` |
| 깨진 문자 비율 | `> broken_char_warn` | `warning` | `broken_char_warn` |
| 페이지당 블록 수 | `< blocks_per_page_warn` | `warning` | `blocks_per_page_warn` |
| `parser_warning` 개수 | `>= max_parser_warnings` | `warning` | `max_parser_warnings` |
| 표 추출 실패 (일반) | 실패 | `warning` | — |
| 표 추출 실패 (하네스) | 실패 | `manual_correction_required` | — |
| 섹션 구조 감지율 (`heading_ratio`) | `< min_heading_ratio` | `warning` | `min_heading_ratio` |
| 표 헤더 유효성 (`valid_table_ratio`) | `< min_valid_table_ratio` | `warning` | `min_valid_table_ratio` |
| 구조적 청크 비율 (`structural_chunk_ratio`) | `< min_structural_chunk_ratio` | `warning` | `min_structural_chunk_ratio` |

> `warning`이 `warn_threshold_count` 이상 누적 시 `manual_correction_required`로 격상.

## 에러 코드

| 에러 코드 | 설명 | 처리 방법 |
|----------|------|----------|
| `E0201` | 지원하지 않는 파일 형식 | 업로드 실패 + 지원 형식 안내 |
| `E0202` | 파일 손상 또는 읽기 실패 | 파싱 실패 + 재업로드 요청 |
| `E0203` | 텍스트 추출 실패 | `failed` 상태 + 수동 입력 유도 |
| `E0204` | 표 추출 실패 | 일반: `warning` / 하네스: `manual_correction_required` |
| `E0205` | HWP 파서 제한 지원 실패 | 제한 지원 안내 + HWPX/DOCX 변환 권고 |
| `E0208` | HWPX XML 파싱 실패 | 수동 텍스트 입력 유도 |
| `E0211` | 파서 결과 품질 부족 | `manual_correction_required` 상태 전환 |
| `E0212` | OCR 필요 문서 감지 (스캔 PDF) | MVP 제외 안내 + 텍스트 기반 PDF 변환 권고 |
| `E0309` | `source_ref` 누락 (strict 모드) | 누락 블록 목록 포함 |
| `E0310` | `block_id` 누락 (strict 모드) | 누락 블록 목록 포함 |

## 저장 테이블 (REQ-001)

| 테이블명 | 저장 내용 |
|---------|----------|
| `parsed_documents` | 파일 메타, 파서 결과, 품질 상태, `parse_version` |
| `document_chunks` | 청크 데이터, `source_ref`(bbox 포함), 토큰 수, `importance_score` |
| `parser_logs` | 파서 실행 이력, warnings, 처리 시간(단계별) |
| `quality_gate_logs` | 판단 기준값, 결과, `quality_metrics`(신규 지표 포함) |

> PII 마스킹 이후의 데이터만 저장. 원본 민감정보는 저장하지 않는다.
> 동일 `workflow_id`로 재처리 시 `parse_version`을 증가시켜 신규 버전으로 삽입.

## analysis_results 책임 경계

본 모듈은 DocumentBlock + chunks + parser_logs + quality_gate_logs만 작성하고, `parsed_documents.status`를 `'ready'`로 설정한 후 다음 파트에 신호만 전달한다. **Gemma4 분석 결과 (`analysis_results` 테이블) 는 REQ-004 FR-LGA-10 (Document Analysis Service) 가 INSERT** 한다.

## 성능 요구사항

| 처리 유형 | 목표 처리 시간 | 비고 |
|----------|-------------|------|
| TXT / CSV / 짧은 DOCX | 30초 이내 | 동기 처리 |
| 일반 PDF / DOCX / PPTX | 60초 이내 | 동기 처리 |
| HWP / HWPX 제한 지원 | 60~120초 | 파서 성공 여부에 따라 편차 큼 |
| 대용량·복잡 표 문서 | 비동기 또는 보정 전환 | Phase 2 대상 |
| OCR 필요 문서 (스캔 PDF) | MVP 제외 | 처리 불가 안내 후 대안 제시 |

## 범위 제외

- LLM 분석 (Gemma4 등) — AI_Agent 파트 담당
- `E03xx` 에러 코드 (`E0309`/`E0310` 제외) — AI_Agent 파트 담당
- 스캔 PDF OCR — Phase 2
- 이미지 내 텍스트 추출 — Phase 2
- HWP 고급 서식 보존 및 복잡 표 복원 — Phase 2
- PII 마스킹 원복 — Phase 2
- BGE-M3 임베딩 생성 — AI_Agent(REQ-004) 담당

## 테스트

```bash
pytest modules/doc-parser/tests/
```
