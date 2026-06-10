# ADR-0019: Vision Pipeline 도입 — fitz(PyMuPDF) + Gemma4 + 인터리빙 패턴

- **Status**: Accepted
- **Date**: 2026-05-21
- **Deciders**: @wlsgud76 (김진형, REQ-006)
- **Reviewers/Informed**: @dhwang0803-glitch (조장), @billionaireahreum (박아름)
- **Tags**: area/doc_parser, layer/adapters, vision

## Context

REQ-006 doc_parser는 8종 포맷(PDF/DOCX/XLSX/CSV/PPTX/HWP/HWPX/MD)의 텍스트 추출을 담당한다.
기본 파서(pdfplumber, python-docx, openpyxl 등)로 텍스트/표를 추출하면 다음 케이스를 처리하지 못한다:

- 이미지로 박힌 표 (PDF/PPTX 스캔 영역)
- 그래프/차트 이미지 (데이터 수치 포함)
- 깨진 텍스트 (broken_char_ratio 초과)
- XLSX 차트 객체

이를 보완하기 위해 **비전 모델을 보조 수단으로 통합**하는 설계가 필요했다.

### 검토된 초기 접근

**LibreOffice 기반 캡처 방식** — 문서를 LibreOffice로 PNG 변환 후 전체 페이지를 Gemma4에 전달하는 FULL_PAGE 전략을 초기에 설계했으나 다음 문제가 발견됐다:

1. **LibreOffice가 HWP 포맷 인식 불가** (Windows 환경 확인)
2. **DOCX는 XML 순회로 충분** — python-docx element.body 전체 순회로 본문/표 원문 순서 보존 가능
3. **전체 페이지 캡처(FULL_PAGE)는 불필요한 비전 호출 증가** — 텍스트 파서가 이미 읽은 내용까지 중복 처리
4. **처리 속도 저하** — 페이지당 15~20초 소요, 포맷별 분기 경로 복잡

## Decision

### 1. LibreOffice 제거 → fitz(PyMuPDF) 기반 캡처

LibreOffice를 전면 제거하고 fitz(PyMuPDF)로 대체한다.

- PDF/HWPX/PPTX → fitz가 직접 페이지 PNG 렌더링 (zoom=2.0, 144dpi)
- LibreOffice HWP→PDF→PNG 변환 경로 폐기
- `VisionExtractor._capture_page()` = fitz 기반 단일 메서드

### 2. FULL_PAGE 전략 폐기 → VisionType 4종으로 단순화

전체 페이지 찰칵 전략을 폐기하고 **감지된 블록만 비전 처리**하는 원칙으로 전환한다.

```
VisionType (4종)
  TABLE     → 표 구조 감지 (block_type="table")
  GRAPH     → 그래프/이미지 감지 (block_type="image")
  CHART     → XLSX 차트 객체 감지
  CORRUPTED → 깨진 텍스트 감지 (broken_char_ratio > 0.1)
```

FULL_PAGE 제거 근거:
- DOCX → XML 순회로 처리 (비전 불필요)
- HWP → hwp5html primary + hwp5txt fallback (LibreOffice 드랍)

### 3. InterleavingParser — 포맷 분기 없이 VisionType으로만 제어

포맷별 분기(`_DOCX_MIME`, `_FULL_PAGE_MIME`)를 제거하고 단일 경로로 통일한다.

```
CSV/MD → 비전 스킵
나머지 전부 → _parse_interleaving() 단일 경로
  TableDetector → TABLE / GRAPH / CHART / CORRUPTED 판단
  감지 없으면 → 텍스트 그대로 통과
  감지 시 → 해당 페이지만 fitz 캡처 → Gemma4(Modal) 호출
  페이지당 최대 1회 비전 호출
```

### 4. VisionPromptStrategy → adapters/vision/prompts.py 분리

프롬프트 텍스트는 정책 변경이 잦은 객체라 domain에서 adapters로 분리한다.

```
domain/entities/vision_type.py  → VisionType enum만
adapters/vision/prompts.py      → VisionPromptStrategy (Gemma4 프롬프트 정책)
```

### 5. ParserFactory → adapters/parser_factory.py 이동

순환 import 방지를 위해 `domain/services/`에서 `adapters/`로 이동한다.
`from_yaml(config_path)` 클래스 메서드를 추가해 `parser_quality.yaml`에서 설정값을 주입받는다.

### 6. Gemma4 연결 — Modal DI 패턴

```python
# Composition Root에서 조립 (services/api_server/dependencies/ 등)
factory = ParserFactory.from_yaml("config/parser_quality.yaml", llm=composition_root_llm)
```

Modal 워크스페이스: `flowit`, 구현체: `LLMBase` (`services/agents/llm-base/`)

## Consequences

### Positive

- **처리 경로 단순화** — 포맷별 분기 제거, `_parse_interleaving()` 단일 경로
- **LibreOffice 의존 제거** — 설치/환경 의존성 0, Windows/Linux 환경 차이 해소
- **불필요한 비전 호출 제거** — 텍스트 파서가 읽은 내용은 비전 스킵, 페이지당 최대 1회
- **포맷 추가 시 확장 용이** — VisionType에 새 타입 추가만으로 처리 가능
- **속도 개선** — FULL_PAGE 전략 대비 비전 호출 횟수 대폭 감소

### Negative / Trade-offs

- **이미지로만 구성된 표/도형 deep-mode 미구현** — 기본 파서가 못 읽는 이미지성 요소를 deep-mode에서 추가 보강하는 작업은 **페이즈2 이관** (정책 변경 수준)
- **HWP 비전 커버리지 제한** — hwp5html/hwp5txt 추출 품질에 의존, LibreOffice 제거로 deep fallback 불가
- **XLSX 병합셀 ContentBlock.table 타입 미스매치** — `list[dict]` → `list[list[Any]]` 불일치, `common_schemas.ContentBlock.metadata` 필드 추가 후 해결 예정 (황대원님 협의 필요)

### Follow-ups

- ⏳ `common_schemas.ContentBlock.metadata: Optional[dict[str, Any]] = None` 추가 (황대원님 협의)
- ⏳ `common_schemas.ContentBlock.is_corrupted: bool = False` 추가 (황대원님 협의)
- ⏳ Vision deep-mode 분리 (페이즈2) — 이미지로 박힌 표/도형 선별 캡처 + supplemental block 병합
- ⏳ fitz + Modal Gemma4 통합 테스트 (`tests/integration/`) 추가
- ⏳ `ParseCoverage.vision_blocks` / `failed_blocks` 전달 경로 확정 (DocumentBlock 필드 추가, 황대원님 협의)

## Alternatives Considered

### A. LibreOffice 유지 + FULL_PAGE 전략

- 장점: 구현 단순 (전체 페이지를 무조건 비전 처리)
- 단점: HWP 인식 불가 확인, 불필요한 비전 호출 증가, 속도 저하 (페이지당 15~20초)
- **기각 사유**: LibreOffice HWP 인식 불가 + 처리 속도 문제

### B. LibreOffice 유지 + 포맷별 분기

- 장점: 포맷 특성에 맞는 세밀한 전략
- 단점: 분기 경로 복잡, DOCX/HWP는 어차피 비전 불필요
- **기각 사유**: 불필요한 복잡도, HWP LibreOffice 인식 불가

### C. 본 결정 — fitz + VisionType 4종 + 인터리빙 패턴

- ✅ 채택 — 단순한 구조, 필요한 블록만 비전 처리

## References

- PR #60: `feat(REQ-006): vision pipeline 도입 + parser 5종 정비 + XLSX styles.xml fix`
- `docs/specs/REQ-006-doc-parser.md` — vision 컴포넌트 전체 반영 (본 ADR과 동시 갱신)
- `modules/doc_parser/adapters/vision/` — VisionExtractor, TableDetector, VisionPromptStrategy
- `modules/doc_parser/adapters/interleaving_parser.py` — 인터리빙 지휘자
- `config/parser_quality.yaml` — broken_char_warn: 0.1 (비전 트리거 임계값)
