# nodes_graph (REQ-003) 결과 보고서

**모듈**: nodes_graph  
**REQ**: REQ-003  
**작성일**: 2026-05-06 (최종 수정: 2026-05-09)  
**담당자**: 박아름  
**브랜치**: `feature/req-003-nodes-graph`  
**상태**: ✅ PASS 완료 (PR #30 4차 리뷰 + 스펙 전수 대조 완료 — Approve 대기 중)

---

## 1. 개발 결과

### 대상 계층

| 계층 | 파일 수 | 주요 구현 |
|------|--------|----------|
| domain/entities | 3 | `NodeDefinition`, `NodeMetadata`, `BaseNode` |
| domain/ports | 2 | `NodeDefinitionRepository`, `EmbedderPort` |
| domain/services | 2 | `GraphValidator`, `GraphSerializer` |
| application/use_cases | 3 | `ValidateGraphUseCase`, `SearchNodesUseCase`, `RegisterNodesUseCase` |
| application | 1 | `catalog_registry` — `get_all_node_definitions()` (domain 28종 + adapters 2종 조합) |
| adapters | 1 | `ToolToNodeWrapper` |
| domain/catalog/data | 14 | `text_transform`, `json_extract`, `json_merge`, `csv_parse`, `csv_build`, `number_calc`, `date_format`, `list_filter`, `list_map`, `string_template`, `regex_extract`, `regex_replace`, `base64_encode`, `base64_decode` |
| domain/catalog/control | 8 | `if_condition`, `switch_case`, `loop_list`, `loop_count`, `delay`, `retry`, `merge_branch`, `stop_workflow` |
| domain/catalog/trigger | 6 | `schedule_trigger`, `webhook_trigger`, `manual_trigger`, `file_watch_trigger`, `event_trigger`, `api_poll_trigger` |
| adapters/catalog/external | 2 | `http_request`, `pdf_generate` (외부 I/O 라이브러리 — adapter 계층으로 분리) |

### 주요 구현 내용

- `GraphValidator`: Kahn's algorithm 기반 사이클 감지 + 고립 노드 + 타입 호환성(stub) + 중복 ID + 필수 연결 누락 5종 검증
- `GraphSerializer`: Pydantic v2 `model_dump/model_validate` 래핑, 역직렬화 실패 시 `ValidationError` raise
- `NodeDefinition`: H-4 합의 준수 — `risk_level`, `required_connections`, `service_type` 필드 포함 (REQ-002가 필드 접근으로 사용)
- H-1 합의 준수 — `WorkflowSchema`, `NodeInstance`, `Edge`, `Position` 자체 정의 없음, 전부 `common_schemas` import
- `pyproject.toml`: 하이픈 디렉토리(`nodes_graph`) 문제 해결을 위해 `package-dir` 명시적 매핑 사용
- **노드 카탈로그 30종** (3계층 분리): `BaseNode` + `NodeDefinition` 패턴으로 일관 구현. `uuid5(_CATALOG_NS, node_type)`으로 UUID 안정성 보장
  - `domain/catalog/` (28종): 순수 비즈니스 로직 노드 — 표준 라이브러리만 사용
  - `adapters/catalog/external/` (2종): httpx/fpdf2 의존 노드 — adapter 계층 격리
  - `application/catalog_registry.py`: `get_all_node_definitions()` — domain 28종 + adapters 2종 조합. `RegisterNodesUseCase` 연동 준비 완료
  - 나머지 24종(AI/LLM 10, 데이터 소스 5, 문서 생성 4, 커뮤니케이션 2, 트리거 2, 외부 1)은 외부 서비스 인증(Google/Slack 등) 필요 — 이후 스프린트 범위

---

## 2. 테스트 결과

### 요약

| 구분 | 건수 |
|------|------|
| 전체 테스트 | 72건 |
| PASS | 72건 |
| FAIL | 0건 |
| SKIP | 0건 |

### 계층별 결과

| 계층 | 전체 | PASS | FAIL |
|------|------|------|------|
| unit/domain | 62 | 62 | 0 |
| unit/application | 10 | 10 | 0 |
| integration | 0 | - | - |

### 테스트 파일 목록

| 파일 | 테스트 케이스 |
|------|-------------|
| `unit/domain/test_node_definition.py` | 생성, 필드 검증, 불변성 |
| `unit/domain/test_graph_validator.py` | 유효/사이클/고립/중복ID/필수연결/타입호환성(stub) 8건 |
| `unit/domain/test_graph_serializer.py` | 직렬화, 역직렬화 왕복, 오류 처리 |
| `unit/domain/test_data_nodes.py` | 데이터 처리 14종 노드 process() 로직 24건 |
| `unit/domain/test_control_nodes.py` | 조건/제어 7종 노드 process() 로직 13건 (stop_workflow 예외 포함) |
| `unit/domain/test_catalog.py` | 카탈로그 통합: 30종 등록, UUID 유일성, node_type 유일성, 트리거 패스스루, api_poll diff 감지 9건 |
| `unit/application/test_validate_graph_use_case.py` | 유효/댕글링엣지/사이클 |
| `unit/application/test_search_nodes_use_case.py` | 검색, limit, 빈 결과 |
| `unit/application/test_register_nodes_use_case.py` | 등록 건수, 임베딩 생성, 기존 임베딩 유지, 저장 확인 |

---

## 3. Review Findings

| 점검 축 | 발견 건수 | 최고 심각도 |
|---------|---------|-----------|
| Correctness | 0 | - |
| Error handling | 0 | - |
| Test coverage | 0 | - |
| Performance | 0 | - |
| API 설계 | 0 | - |
| Clean Architecture | 0 | - |
| Readability | 0 | - |

Critical/Major 없음. (PR #30 1~3차 리뷰를 통해 모두 해소)

---

## 4. Clean Architecture 준수 점검

- [x] 의존성 방향 위반 0건 (domain/application에 FastAPI/SQLAlchemy import 없음)
- [x] ORM 모델 도메인 누출 0건
- [x] 공유 타입 SSOT 준수 (`WorkflowSchema`, `NodeInstance`, `Edge` → `common_schemas`)
- [x] H-1 합의 준수 — 자체 WorkflowSchema/NodeInstance/Edge 정의 없음
- [x] H-4 합의 준수 — NodeDefinitionRepository에 get_risk_level() 등 추가 없음
- [x] domain 계층에서 외부 I/O 라이브러리(httpx, fpdf2) import 없음 — adapters 격리
- [x] domain → adapters 역방향 import 없음 — `get_all_node_definitions()` application 계층으로 이동
- [x] `string.Template.safe_substitute()` 사용 — format injection 차단

---

## 5. 오류 원인 분석

해당 없음 (72/72 PASS)

---

## 6. 개선 내용 (실제 적용)

| 항목 | 내용 | 이유 |
|------|------|------|
| `pyproject.toml` package-dir 명시 | `nodes_graph` 디렉토리 언더스코어 전환 → `package-dir` 매핑으로 해결 | Python 패키지명 하이픈 불허 |
| Ruff lint 수정 (18건 자동 + 4건 수동) | import 정렬(I001), `Optional[X]`→`X \| None`(UP045), 세미콜론 분리(E702), 줄 길이 초과(E501) | Ruff line-length=120 준수 |
| `domain/services/graph_validator.py` | `_check_type_compatibility()` 메서드 추가, `validate()` 파이프라인 편입 (stub) | docs/specs 5종 검증 항목 완성 (2026-05-07, REQ-004 연동 시 구체화) |
| `domain/services/graph_validator.py` | `validate()` docstring 순서를 실제 코드 실행 순서와 일치 | 조장 리뷰 반영: 문서-코드 정합 (2026-05-08, PR #17) |
| `adapters/tool_to_node_wrapper.py` | `tool: Any` → `tool: "BaseTool"` (TYPE_CHECKING 블록 활용) | 조장 리뷰 반영: spec 준수, IDE 타입 지원 확보 (2026-05-08, PR #17) |
| `adapters/tool_to_node_wrapper.py` | uuid5 namespace를 `_TOOL_NAMESPACE` 프로젝트 전용 상수로 변경 | 조장 리뷰 반영: DNS namespace 직접 사용 제거 (2026-05-08, PR #17) |
| `tests/unit/domain/test_graph_validator.py` | `test_type_compatibility_returns_no_errors` 추가 | 조장 리뷰 반영: 5종 검증 전부 테스트 커버 (2026-05-08, PR #17) |
| `domain/catalog/` + `adapters/catalog/external/` 신설 (30종 노드) | `domain/catalog/`: `_catalog_ns.py`, `data/`(14), `control/`(8), `trigger/`(6) / `adapters/catalog/external/`: `http_request`, `pdf_generate` | 54종 MVP 중 외부 서비스 인증 불필요한 30종 선구현. httpx/fpdf2 의존 노드는 adapter 계층 분리. `get_all_node_definitions()`로 RegisterNodesUseCase 연동 준비 |
| Ruff E501 수정 (카탈로그 파일 2건) | `if_condition.py:90`, `number_calc.py:87` enum 목록 줄 분리 | line-length=120 준수 |
| `tests/unit/domain/test_data_nodes.py` 신설 | 데이터 처리 14종 24건 | 카탈로그 노드 process() 로직 검증 |
| `tests/unit/domain/test_control_nodes.py` 신설 | 조건/제어 7종 13건 | StopWorkflowError 예외 포함 |
| `tests/unit/domain/test_catalog.py` 신설 | 카탈로그 통합 9건 | 30종 등록, UUID/type 유일성, 트리거 패스스루 |
| **[PR #30 1차 리뷰]** `catalog/` → `domain/catalog/` 이동 | 30개 노드 파일 import depth 수정, 테스트 import 경로 수정 | Clean Architecture 3계층 바깥 위치 해소 (2026-05-08) |
| **[PR #30 1차 리뷰]** `pyproject.toml` requires-python `>=3.11` → `>=3.12` | `_test_db.py` → `scripts/` 이동 | Python 버전 통일, 파일 위치 컨벤션 (2026-05-08) |
| **[PR #30 2차 리뷰]** `domain/catalog/external/` → `adapters/catalog/external/` 이동 | httpx/fpdf2 import를 domain에서 adapters로 격리 | domain 계층 외부 I/O 라이브러리 금지 원칙 준수 (2026-05-08) |
| **[PR #30 2차 리뷰]** `string_template.py` `str.format()` → `string.Template.safe_substitute()` | 템플릿 형식 `{변수명}` → `$변수명` | format injection 차단 (2026-05-08) |
| **[PR #30 3차 리뷰]** `application/catalog_registry.py` 신설 | `get_all_node_definitions()` domain → application 이동 | domain이 adapters를 역참조하던 구조 해소 (2026-05-09) |
| **[PR #30 3차 리뷰]** `domain/catalog/__init__.py` 정리 | `get_domain_node_definitions()` 28종만 노출, adapters import 완전 제거 | 단방향 의존성 완성 (2026-05-09) |
| **[PR #30 3차 리뷰]** `domain/catalog/external/__init__.py` 삭제 | 빈 파일 제거 | 불필요 파일 정리 (2026-05-09) |
| **[PR #30 3차 리뷰]** `scripts/_test_db.py` .env 경로 수정 | `parent.parent / ".env"` → 프로젝트 루트 참조 | 실제 .env 위치와 일치 (2026-05-09) |
| **[PR #30 4차 리뷰]** `HttpRequestNode` risk_level `MEDIUM` → `HIGH` | NodeMetadata, get_node_definition() 둘 다 변경 | 임의 URL DELETE/POST 가능 → 비가역적 외부 변경, REQ-005 기준 일치 (2026-05-09) |
| **[스펙 전수 대조]** control 8종 category `"조건/제어"` → `"조건 / 제어"` | 슬래시 양옆 공백 추가 (8개 파일 × 2곳) | REQ-003 스펙 카테고리명과 정확히 일치 (2026-05-09) |

### Ruff lint 최종 결과

```
All checks passed! (N999 제외 — nodes_graph 디렉토리 구조상 불가피)
```

---

## 7. 다음 단계 권고사항

- ~~**REQ-002 (auth) 연동**: `CredentialInjectionService`에 `NodeDefinitionRepository` 주입 및 `node_id` 파라미터 추가~~ → ✅ 완료 (2026-05-07, auth PR #19)
- **REQ-004 (ai_agent) 연동**: `GraphValidator`, `SearchNodesUseCase` 소비 — `NodeRegistry` 퍼사드로 래핑 예정
- **`_check_type_compatibility` 구체화**: REQ-004 `NodeDefinition` handle 타입 메타데이터 확보 후 실제 검증 로직 구현 필요
- **REQ-008 (storage) 연동**: `NodeDefinitionRepository` ABC 구현체 작성 필요 (pgvector `search_by_embedding` 포함)
- **integration 테스트**: `search_by_embedding()` 실제 벡터 검색은 pgvector 환경 구성 후 작성 권장
- **카탈로그 나머지 24종**: AI/LLM(10), 데이터 소스(5), 문서 생성(4), 커뮤니케이션(2), 트리거(2), 외부(1) — 외부 서비스 OAuth/Credential 연동 후 구현 (REQ-002, REQ-005 완료 후)
- **카탈로그 DB 등록**: `RegisterNodesUseCase.execute(get_all_node_definitions())` — REQ-008 storage 완료 후 실행
