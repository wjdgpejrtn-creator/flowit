# REQ-003 Nodes-Graph 모듈 구현 Plan

**브랜치**: `feature/req-003-nodes-graph`  
**담당자**: 박아름  
**작성일**: 2026-05-06  
**참조 스펙**: `docs/specs/REQ-003-nodes-graph.md` (development 브랜치)  
**참조 ADR**: H-1 (WorkflowSchema SSOT), H-4 (NodeDefinitionRepository 메서드)

---

## 구현해야 하는 클래스 목록

### Domain Layer

| 클래스 | 파일 경로 | 상태 |
|--------|-----------|------|
| `NodeDefinition` | `domain/entities/node_definition.py` | ✅ 완료 |
| `NodeMetadata` | `domain/entities/node_metadata.py` | ✅ 완료 |
| `BaseNode` (ABC, Generic) | `domain/entities/base_node.py` | ✅ 완료 |
| `GraphValidator` | `domain/services/graph_validator.py` | ✅ 완료 (`_check_type_compatibility` stub 포함) |
| `GraphSerializer` | `domain/services/graph_serializer.py` | ✅ 완료 |
| `NodeDefinitionRepository` (ABC) | `domain/ports/node_definition_repository.py` | ✅ 완료 |
| `EmbedderPort` (ABC) | `domain/ports/embedder_port.py` | ✅ 완료 |

### Application Layer

| 클래스 | 파일 경로 | 상태 |
|--------|-----------|------|
| `ValidateGraphUseCase` | `application/use_cases/validate_graph_use_case.py` | ✅ 완료 |
| `SearchNodesUseCase` | `application/use_cases/search_nodes_use_case.py` | ✅ 완료 |
| `RegisterNodesUseCase` | `application/use_cases/register_nodes_use_case.py` | ✅ 완료 |

### Adapter Layer

| 클래스 | 파일 경로 | 상태 |
|--------|-----------|------|
| `ToolToNodeWrapper` | `adapters/tool_to_node_wrapper.py` | ✅ 완료 |

---

## 사용해야 하는 클래스 목록 (common-schemas import)

| 클래스 | import 경로 | 사용처 |
|--------|-------------|--------|
| `WorkflowSchema` | `common_schemas` | `GraphValidator.validate()` 입력, `GraphSerializer` 입출력 |
| `NodeInstance` | `common_schemas` | `GraphValidator` 내부 노드 순회 |
| `NodeConfig` | `common_schemas` | `NodeDefinition` 상위 구조 참조 |
| `Edge` | `common_schemas` | `GraphValidator` 엣지 순회 |
| `Position` | `common_schemas` | `NodeInstance.position` 타입 |
| `ValidationErrorItem` | `common_schemas` | `GraphValidator` 검증 에러 항목 |
| `ValidationErrorResponse` | `common_schemas` | `GraphValidator.validate()` 반환 타입 |
| `RiskLevel` | `common_schemas.enums` | `NodeDefinition.risk_level` 타입 |
| `ErrorCode` | `common_schemas.enums` | 검증 에러 코드 (`E_CYCLE_DETECTED`, `E_ISOLATED_NODE` 등) |
| `ValidationError` | `common_schemas.exceptions` | 스키마 검증 실패 시 raise |
| `NotFoundError` | `common_schemas.exceptions` | 노드 미발견 시 raise |

---

## 핵심 구현 상세

### GraphValidator 검증 항목 (5종)

| 검증 | 알고리즘 | ErrorCode |
|------|---------|-----------|
| 사이클 감지 | Kahn's algorithm (위상 정렬 기반) | `E_CYCLE_DETECTED` |
| 고립 노드 | 연결된 엣지가 없는 노드 | `E_ISOLATED_NODE` |
| 타입 불일치 | from_handle ↔ to_handle 타입 호환 | `E_NODE_TYPE_MISMATCH` |
| 중복 instance_id | set으로 O(n) 검출 | `E_DUPLICATE_ID` |
| 필수 연결 누락 | NodeDefinition.required_connections 확인 | `E_MISSING_CONNECTION` |

### H-1 합의 준수 (절대 위반 금지)

- `WorkflowSchema`, `NodeInstance`, `Edge`, `Position` 자체 정의 **금지**
- 반드시 `from common_schemas import ...` 로만 사용

### H-4 합의 준수

- `NodeDefinitionRepository` ABC에 `get_service_type()`, `get_risk_level()` 등 추가 **금지**
- `get_by_id()` 반환 `NodeDefinition` 객체의 필드로 접근

### EmbedderPort 사용 범위

- `SearchNodesUseCase`, `RegisterNodesUseCase`에서 의존성 주입으로만 사용
- 구현체(BGE-M3)는 ai-agent 모듈 담당 → 이 모듈에서 구현하지 않음

---

## 테스트 목록

### unit/domain

| 테스트 파일 | 테스트 대상 | 상태 |
|-------------|-------------|------|
| `test_node_definition.py` | `NodeDefinition` 생성, 필드 검증 | ✅ 완료 |
| `test_graph_validator.py` | 사이클/고립/타입불일치/중복ID/필수연결 5종 검증 | ✅ 완료 |
| `test_graph_serializer.py` | `serialize()` / `deserialize()` 왕복 | ✅ 완료 |

### unit/application

| 테스트 파일 | 테스트 대상 | 상태 |
|-------------|-------------|------|
| `test_validate_graph_use_case.py` | 유효/무효 그래프 분기 | ✅ 완료 |
| `test_search_nodes_use_case.py` | 쿼리 → 임베딩 → 검색 결과 | ✅ 완료 |
| `test_register_nodes_use_case.py` | 노드 등록 + 임베딩 생성 | ✅ 완료 |

---

## 구현 순서 (Clean Architecture 원칙)

```
1. common-schemas 타입 확인 완료 ✅
2. domain/entities: NodeDefinition → NodeMetadata → BaseNode
3. domain/ports: NodeDefinitionRepository ABC → EmbedderPort ABC
4. domain/services: GraphValidator → GraphSerializer
5. application/use_cases: ValidateGraphUseCase → SearchNodesUseCase → RegisterNodesUseCase
6. adapters: ToolToNodeWrapper
7. tests: unit/domain → unit/application
```

---

## 의존성 관계

```
이 모듈 → common-schemas (WorkflowSchema, NodeInstance, Edge, ValidationErrorResponse 등)
이 모듈 ← auth (REQ-002): NodeDefinitionRepository.get_by_id() 후 NodeDefinition 필드 접근
이 모듈 ← ai-agent (REQ-004): GraphValidator 호출, SearchNodesUseCase 소비
이 모듈 ← execution-engine (REQ-007): 위상 정렬 실행 순서 결정
이 모듈 ← storage (REQ-008): NodeDefinitionRepository 구현체 제공
```

---

## 미결 사항

| 항목 | 이유 | 해결 조건 |
|------|------|-----------|
| `EmbedderPort` 구현체 | BGE-M3 구현은 ai-agent(REQ-004) 담당 | REQ-004 완성 후 |
| `ToolToNodeWrapper.process()` credential 주입 방식 | REQ-005 BaseTool 인터페이스 미확정 | REQ-005 완성 후 |
| `search_by_embedding()` 실제 벡터 검색 | pgvector 환경 필요 | REQ-008 storage 구성 후 integration 테스트 |

---

## 완료 체크리스트

- [x] domain/entities 전체 구현
- [x] domain/ports 전체 구현
- [x] domain/services 전체 구현
- [x] application/use_cases 전체 구현
- [x] adapters 구현
- [x] unit/domain 테스트 전체 작성
- [x] unit/application 테스트 전체 작성
- [x] pytest 전체 통과 (25/25 PASS)
- [x] Ruff lint 통과
- [x] report 작성 (`modules/nodes-graph/report/`)
- [x] PR → `development` 브랜치
