# 클래스 다이어그램 교차분석 — 해결 제안서

- **작성일**: 2026-05-04
- **작성자**: 황대원 (조장)
- **목적**: 교차 정적분석에서 발견된 이슈별 해결 방향을 제안하고, 팀 논의를 통해 합의안을 확정한다.
- **참조**: `docs/class_diagram_review.md` (교차분석 보고서)

---

## 공통 원칙

아래 제안은 세 가지 원칙에 기반한다.

| 원칙 | 설명 |
|------|------|
| **SSOT (Single Source of Truth)** | 공유 타입은 REQ-012 Common Schemas에 단일 정의하고, 다른 REQ는 import한다. 중복 정의는 런타임 직렬화/역직렬화 에러의 근본 원인이 된다. |
| **도메인 소유권** | 각 타입은 해당 도메인을 가장 잘 이해하는 REQ가 소유한다. 소유 REQ가 인터페이스를 정의하면, 다른 REQ는 이를 구현하거나 import한다. |
| **합집합 확장** | 여러 REQ가 같은 타입에 서로 다른 필드를 정의한 경우, SSOT에 합집합을 반영하되 기존 REQ에 없는 필드는 `Optional`로 추가하여 하위호환을 유지한다. |

---

## HIGH 이슈 해결 제안

### H-1. WorkflowSchema / NodeInstance / Edge 중복 (REQ-003 vs REQ-012)

**제안: REQ-003의 자체 정의 삭제 → REQ-012 import** - 확정

| 변경 항목 | 현재 | 변경 후 |
|-----------|------|---------|
| REQ-003 WorkflowSchema | 자체 정의 (description 포함) | REQ-012 import |
| REQ-003 NodeInstance.instance_id | `str` | `UUID` (REQ-012 기준) |
| REQ-003 NodeInstance.position | `dict` | `Position` VO (REQ-012 기준) |
| REQ-012 WorkflowSchema | description 없음 | `description: Optional[str]` 추가 |

**근거:**
- REQ-012는 프로젝트 설계 시점부터 "공유 스키마 단일 정의"를 목적으로 만들어진 모듈이다. REQ-003이 동일 타입을 재정의하면, 두 모듈을 함께 import하는 코드에서 이름 충돌 또는 타입 불일치가 발생한다.
- `instance_id: str` vs `UUID`는 단순 취향이 아니라 **FK 참조 무결성**에 영향을 준다. DB 레이어(REQ-001)가 UUID를 PK로 사용하므로, 도메인 모델도 UUID로 맞추지 않으면 매 호출마다 타입 변환이 필요해진다.
- `position: dict`는 타입 안전성이 없어 `{"x": "문자열"}` 같은 잘못된 값이 런타임까지 도달할 수 있다. `Position` VO로 통일하면 Pydantic 검증이 자동 적용된다.

**작업자**: 박아름(REQ-003 수정) + 황대원(REQ-012에 description 추가)

---

### H-2. 암호화 클래스 중복 + 시그니처 불일치 (REQ-001 vs REQ-002)

**제안: REQ-002(Auth-Security)가 cipher 소유, REQ-001은 DI로 주입받는 구조** - 확정

| 변경 항목 | 현재 | 변경 후 |
|-----------|------|---------|
| cipher 소유 | REQ-001 `EncryptionStrategy` + REQ-002 `BaseCipher` | REQ-002 `BaseCipher`만 유지 |
| REQ-001 | 자체 cipher 정의 | REQ-002 cipher를 생성자 주입 |
| encrypt 시그니처 | REQ-001 `bytes→bytes`, REQ-002 `str→bytes` | `bytes→bytes` 통일 |
| 구현체명 | `AesGcmCipher` / `AESGCMCipher` | `AESGCMCipher` (REQ-002 기준) |

**근거:**
- **도메인 소유권 원칙**: 암호화는 인증·보안 도메인의 핵심 관심사이다. REQ-002(Auth-Security)가 알고리즘 선택·키 관리·회전 정책까지 책임지는 것이 자연스럽고, REQ-001(Database)은 "어떤 cipher든 주입받아 필드를 암호화/복호화한다"는 역할만 갖는다.
- **시그니처 `bytes→bytes` 선택 이유**: DB에 저장되는 데이터는 바이너리(bytes)다. `str→bytes`로 하면 cipher 내부에서 인코딩 가정(UTF-8? ASCII?)이 생기고, 비텍스트 데이터(파일, 이미지 해시 등) 암호화 시 별도 경로가 필요해진다. `bytes→bytes`로 통일하면 호출부에서 `.encode()` 한 줄이면 되고, cipher는 인코딩에 무관하게 동작한다.
- **명명 `AESGCMCipher`**: PEP 8은 약어를 대문자로 유지하는 것을 허용한다 (`HTTPServer`, `URLParser`). "AES-GCM"은 하나의 고유 약어이므로 `AESGCM`이 `AesGcm`보다 가독성이 높다.

**작업자**: 황대원(REQ-001 cipher 삭제, DI 전환) + 박아름(REQ-002 시그니처 bytes 통일)

---

### H-3. Repository ABC ↔ 구현체 메서드 시그니처 불일치

**제안: REQ-002 ABC를 계약 기준으로, REQ-001 구현체가 메서드명·시그니처를 맞추기** - 확정

```
SessionRepository (REQ-002 ABC 기준):
  create(user_id, hash) → Session
  find_by_hash(hash) → Session
  revoke(session_id) → None
  revoke_all_for_user(user_id) → int       ← REQ-001에 신규 추가

OAuthConnectionRepository (REQ-002 ABC 기준):
  create(user_id, service, tokens) → Conn
  get_by_credential_id(cid) → Conn         ← REQ-001에 신규 추가
  get_active_for_user(uid, svc) → Conn
  update_tokens(cid, new_tokens) → None
  revoke(cid) → None
```

REQ-001 구현체 매핑:

| REQ-001 현재 | → 변경 후 | 비고 |
|--------------|----------|------|
| `create_session(user_id, kind)` | `create(user_id, hash)` | 메서드명 + 파라미터명 통일 |
| `load(session_id)` | `find_by_hash(hash)` | 조회 키 변경 |
| `flush(session_id)` | `revoke(session_id)` | 메서드명 통일 |
| (없음) | `revoke_all_for_user(user_id)` | 신규 구현 |
| `upsert(connection)` | `create(…)` + `update_tokens(…)` | upsert → 분리 |
| `list(user_id)` | `get_active_for_user(uid, svc)` | 서비스별 필터 추가 |
| `refresh(connection_id)` | `update_tokens(cid, new_tokens)` | 메서드명 + 파라미터 통일 |
| `disconnect(connection_id)` | `revoke(cid)` | 메서드명 통일 |

**근거:**
- **인터페이스 분리 원칙(ISP)**: ABC는 "호출자가 기대하는 계약"이다. REQ-002가 ABC를 정의한 것은 인증 서비스가 Repository에 어떤 동작을 기대하는지를 선언한 것이므로, 구현체(REQ-001)가 이 계약을 충족해야 한다. 반대로 구현체에 맞춰 ABC를 바꾸면 ABC의 존재 의미가 사라진다.
- **반환 타입 통일**: REQ-001의 `ChatSessionModel`(ORM 모델)이 아닌 REQ-002의 `Session`(도메인 모델)을 반환해야 한다. ORM 모델이 서비스 계층까지 누출되면 DB 스키마 변경 시 서비스 코드 전체에 영향이 퍼진다.

**작업자**: 황대원(REQ-001 구현체 리팩터링)

---

### H-4. NodeDefinitionRepository 메서드 불일치 (REQ-002 vs REQ-003)

**제안: ABC에 메서드를 추가하지 않고, `NodeDefinition` 객체의 필드로 해결** - 확정

```
현재 상황:
  REQ-002 필요: get_service_type(node_id), get_required_connections(node_id), get_risk_level(node_id)
  REQ-003 ABC:  get_by_id(node_id) → NodeDefinition

제안:
  node = repo.get_by_id(node_id)
  node.service_type        # ← 필드 접근
  node.required_connections # ← 필드 접근
  node.risk_level          # ← 필드 접근
```

**근거:**
- **Fat Interface 방지**: 특정 소비자(REQ-002)의 편의를 위해 ABC에 메서드를 추가하면, ABC를 구현하는 모든 클래스가 해당 메서드를 구현해야 한다. 지금은 구현체가 하나지만 테스트 Mock, Cache Proxy 등이 추가되면 구현 부담이 곱으로 늘어난다.
- **이미 해결 가능**: REQ-012의 `NodeConfig`에 `risk_level`, `required_connections` 필드가 이미 정의되어 있다. REQ-003의 `NodeDefinition`이 이 필드들을 포함하고 있음을 명시하면 추가 메서드 없이 해결된다.
- **N+1 방지**: 별도 메서드 3개 호출 대신 `get_by_id` 1회 호출 후 필드 접근으로 DB 왕복을 줄인다.

**작업자**: 박아름(REQ-003 NodeDefinition에 해당 필드 존재 명시)

---

### ~~H-5. 파일 형식 문제~~ — 해소됨

REQ-004, REQ-005 모두 `.drawio` 수정본 제출 완료. 파일명 컨벤션은 L-1에서 추적.

---

### H-6. DocumentBlock 중복 정의 (REQ-006 vs REQ-012)

**제안: REQ-012가 REQ-006의 상세 필드를 흡수, REQ-006은 import** - 확정

```
REQ-012 DocumentBlock 최종:
  document_id: UUID                       (str→UUID 통일)
  workflow_id: Optional[UUID]             (REQ-006에서 승격)
  user_id: Optional[UUID]                 (REQ-006에서 승격)
  parser: Optional[ParserMeta]            (REQ-006 객체 타입 채택)
  blocks: list[ContentBlock]              (클래스명 H-8에서 통일)

REQ-006: 자체 DocumentBlock 삭제, REQ-012 import
```

**근거:**
- **SSOT 원칙**: DocumentBlock은 파서(REQ-006)와 AI 분석(REQ-012) 양쪽에서 사용하는 공유 타입이다. 두 곳에서 별도 정의하면, 파서 출력을 AI 분석 입력으로 넘길 때 필드 불일치로 런타임 에러가 발생한다.
- **REQ-006 필드를 SSOT에 반영하는 이유**: REQ-006이 문서 파싱의 도메인 전문가이므로, 파서가 필요로 하는 `workflow_id`, `user_id` 같은 컨텍스트 필드는 실제 파이프라인에서 필수다. REQ-012가 이를 누락한 것은 설계 시점에 파서 요구사항이 반영되지 않은 것이지, 의도적 제외가 아니다.
- **`parser: str` → `ParserMeta` 변경 이유**: 단순 문자열(`"pdf"`)은 파서 버전, 사용된 설정 등 추적이 불가능하다. `ParserMeta` 객체로 하면 재현성(reproducibility)과 디버깅이 용이해진다.
- **`Optional` 선택 이유**: `workflow_id`, `user_id`는 파서 파이프라인에서는 필수지만, 단독 문서 분석(워크플로우 없이 문서만 분석하는 경우)에서는 불필요하므로 Optional이 적절하다.

**작업자**: 황대원(REQ-012 확장) + 김진형(REQ-006 import 전환)

---

### H-7. FileMeta 필드 불일치 (REQ-006 vs REQ-012)

**제안: REQ-012를 REQ-006 수준으로 확장 (합집합)** - 확정

```
REQ-012 FileMeta 최종:
  file_name: str                            (기존)
  file_type: str                            (기존)
  file_size: int                            (기존)
  mime_type: str                            (기존, REQ-006에도 추가)
  page_count: Optional[int]                 (REQ-006에서 승격)
  unit_type: Optional[str]                  (REQ-006에서 승격)
  created_at: Optional[datetime]            (REQ-006에서 승격)
  author: Optional[str]                     (REQ-006에서 승격)
  sheet_meta: Optional[list[SheetMeta]]     (REQ-006에서 승격)
```

**근거:**
- **정보 손실 방지**: REQ-012의 4필드만으로는 엑셀 파일의 시트 구조(`sheet_meta`)나 PDF의 페이지 수(`page_count`)를 표현할 수 없다. 이 정보가 없으면 파서 결과물을 후속 단계(AI 분석, 프론트엔드 미리보기)에서 활용할 때 원본 파일을 다시 열어야 하는 비효율이 발생한다.
- **Optional로 추가하므로 기존 소비자에 영향 없음**: REQ-012의 FileMeta를 이미 사용하는 다른 REQ는 새 필드를 무시해도 동작한다. Pydantic `model_validate`는 Optional 필드가 누락되면 None으로 채우므로 하위호환이 보장된다.
- **`mime_type`을 REQ-006에 추가하는 이유**: `file_type`(확장자 기반 분류)과 `mime_type`(IETF 표준 미디어 타입)은 용도가 다르다. `.xlsx` 파일의 `file_type`은 `"xlsx"`지만 `mime_type`은 `"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"`이다. 외부 시스템(Storage, CDN) 연동 시 mime_type이 필요하다.

**작업자**: 황대원(REQ-012 확장) + 김진형(REQ-006에 mime_type 추가 후 import 전환)

---

### H-8. Block vs ContentBlock 구조 불일치 (REQ-006 vs REQ-012)

**제안: `ContentBlock`으로 클래스명 통일, 필드는 합집합 + Optional** - Optional도 모두 구현하는 것으로 확정.

```
REQ-012 ContentBlock 최종:
  block_id: str
  block_type: Literal["text","table","image","heading","code"]
  content: Optional[str]                    (REQ-012 필드명 유지)
  table: Optional[list[list[Any]]]          (REQ-006에서 승격)
  page: Optional[int]                       (REQ-006에서 승격)
  section_title: Optional[str]              (REQ-006에서 승격)
  bbox: Optional[BBox]                      (REQ-006에서 승격)
  source_ref: Optional[SourceRef]           (dict→VO, M-6 연계)
  token_estimate: Optional[int]             (AI 단계에서 채움)
  importance_score: Optional[float]         (AI 단계에서 채움)
```

**근거:**
- **클래스명 `ContentBlock` 선택 이유**: `Block`은 너무 범용적이다 (UI Block, Storage Block 등과 혼동). `ContentBlock`은 "문서 콘텐츠의 블록 단위"라는 도메인 의미를 명확히 전달하며, 코드 검색 시 의도치 않은 매칭을 줄인다.
- **`text` → `content` 통일 이유**: `text`는 텍스트 블록에만 해당하는 것처럼 보이지만, 실제로는 heading이나 code 블록에도 텍스트 내용이 들어간다. `content`가 블록 종류에 무관하게 "이 블록의 주요 내용"이라는 의미를 더 정확히 전달한다.
- **`table` 필드를 별도로 유지하는 이유**: 테이블 데이터를 `content: str`에 JSON 문자열로 넣는 것은 가능하지만, 행·열 접근 시 매번 파싱이 필요하고 타입 안전성이 없다. `list[list[Any]]`로 별도 필드를 두면 Pandas DataFrame 변환이 직관적이다.
- **`source_ref: dict` → `SourceRef` VO 변경 이유**: `dict`는 어떤 키가 있는지 런타임 전까지 알 수 없다. VO로 바꾸면 IDE 자동완성과 Pydantic 검증이 가능해진다. (M-6과 동시 해결)
- **`block_type`에 `"code"` 추가 이유**: REQ-006 파서가 마크다운·노트북 파일을 처리할 때 코드 블록 분류가 필요하다. REQ-012 원래 4종(`text`, `table`, `image`, `heading`)에 `code`를 추가한다.

**작업자**: 황대원(REQ-012 확장) + 김진형(REQ-006 Block→ContentBlock import 전환)

---

### H-9. AgentState 필드 심각 불일치 (REQ-004 vs REQ-012)

**제안: REQ-012 AgentState를 합집합으로 확장, REQ-004는 import** - 확정

```
REQ-012 AgentState 최종:
  session_id: str                           (REQ-004에서 승격)
  user_id: str                              (REQ-004에서 승격, SHA256 익명화)
  messages: list[BaseMessage]               (REQ-012 타입명 유지)
  turn_count: int                           (REQ-004에서 승격, ≤25)
  mode: AgentMode                           (str→Enum 승격)
  draft_spec: Optional[DraftSpec]           (양쪽 동일)
  intent_result: Optional[IntentResult]     (REQ-012 유지, REQ-004에 추가)
  node_candidates: list[NodeConfig]         (REQ-012 타입명 유지)
  workflow_draft: Optional[WorkflowSchema]  (REQ-012 타입명 유지)
  execution_status: ExecutionStatus         (REQ-004에서 승격)

신규 Enum (REQ-012에 추가):
  AgentMode: ONBOARDING, WIZARD, EDIT, GENERAL, SECURITY
  ExecutionStatus: RUNNING, PAUSED, COMPLETED, FAILED
```

**근거:**
- **`session_id`, `user_id` 승격 이유**: LangGraph의 `thread_id`는 `user_id:session_id` 조합으로 구성된다 (REQ-004 SkillAgent에 명시). 이 두 필드가 AgentState에 없으면 checkpointer가 어떤 대화인지 식별할 수 없다. REQ-012가 누락한 것은 LangGraph 연동 설계가 나중에 구체화되었기 때문이다.
- **`turn_count` 승격 이유**: REQ-004는 25턴 제한을 명시했다. 이 제한이 AgentState에 없으면 보안(무한 루프 방지)과 비용 관리가 불가능하다.
- **`mode: str` → `AgentMode` Enum 변경 이유**: 문자열은 오타(`"wizrd"`)가 런타임까지 도달한다. Enum으로 바꾸면 IDE 자동완성과 Pydantic 검증으로 잘못된 값을 즉시 잡을 수 있다. REQ-004가 5개 모드를 명시했으므로 이를 Enum으로 공식화한다.
- **`messages: list[BaseMessage]` 유지 이유**: LangGraph는 `langchain_core.messages.BaseMessage`를 표준으로 사용한다. REQ-004의 `ChatMessage`가 이를 상속하는 구조라면 타입 호환이 유지되므로, SSOT은 상위 타입인 `BaseMessage`로 선언하는 것이 맞다.
- **`node_candidates: list[NodeConfig]` 유지 이유**: REQ-012의 `NodeConfig`는 12개 필드를 갖는 풍부한 정의다. REQ-004의 `NodeDef`는 같은 개념이나 정의가 보이지 않는 별칭이므로, 이미 잘 정의된 `NodeConfig`를 사용한다.
- **`intent_result`를 REQ-004에 추가하는 이유**: IntentAnalyzerService가 분석 결과를 AgentState에 기록해야 후속 노드(drafter, qa)가 의도(clarify/draft/refine/propose)에 따라 분기할 수 있다. REQ-004 다이어그램에 IntentAnalyzerService가 있으므로 이 필드가 누락된 것은 실수로 보인다.

**작업자**: 황대원(REQ-012 확장) + 신정혜(REQ-004 import 전환, intent_result 추가)

---

### H-10. WorkflowDraft vs WorkflowSchema 3중 정의 (REQ-004 vs REQ-003 vs REQ-012)

**제안: `WorkflowSchema`로 클래스명 통일, REQ-004 고유 필드는 REQ-012에 추가** - 확정

```
REQ-012 WorkflowSchema 최종:
  workflow_id: UUID
  name: str
  description: Optional[str]                (REQ-003에서 승격)
  scope: Literal["private","team","public"]  (소문자 통일)
  is_draft: bool
  draft_spec: Optional[DraftSpec]           (REQ-003의 dict→DraftSpec)
  nodes: list[NodeInstance]                 (REQ-012 기준)
  connections: list[Edge]                   (REQ-012 기준)
  version: Optional[int]                    (REQ-004에서 승격)
  sha256: Optional[str]                     (REQ-004에서 승격)
  created_via_session_id: Optional[UUID]    (REQ-003에서 승격)
  + validate_graph(): bool

REQ-004: WorkflowDraft → WorkflowSchema 클래스명 변경, import
REQ-003: 자체 정의 삭제, import
```

**근거:**
- **`WorkflowSchema` 선택 이유**: 3개 REQ 중 2개(REQ-003, REQ-012)가 이미 `WorkflowSchema`를 사용한다. 다수결 원칙과 함께, "Schema"는 "워크플로우의 구조 정의"를 정확히 표현한다. "Draft"는 상태(초안/확정)를 이름에 포함하는데, 확정된 워크플로우도 같은 클래스를 사용하므로 `is_draft: bool` 필드로 상태를 분리하는 것이 맞다.
- **`version` 승격 이유**: REQ-004의 version 필드는 워크플로우 변경 이력 추적에 필수다. 사용자가 워크플로우를 수정할 때마다 version이 증가하고, 충돌 감지(optimistic locking)에 사용된다.
- **`sha256` 승격 이유**: REQ-004가 무결성 서명용으로 도입했다. 워크플로우가 실행 엔진(REQ-007)에 전달될 때, 전달 과정에서 변조되지 않았음을 검증하는 데 사용된다. 보안 관점에서 유용한 필드다.
- **`scope` 소문자 통일 이유**: REQ-004는 `ScopeEnum`, REQ-012는 `"Private"/"Team"/"Public"` (대문자 시작), REQ-003은 `"private"/"team"/"public"` (소문자). DB 저장 시 대소문자 불일치는 쿼리 오류의 원인이 된다. Python Literal은 대소문자를 구별하므로 하나로 통일해야 하며, JSON/DB 관례상 소문자가 표준이다.
- **`draft_spec: dict` → `DraftSpec` 변경 이유 (REQ-003)**: REQ-003만 `Optional[dict]`로 선언했는데, REQ-012와 REQ-004 모두 `DraftSpec` 타입을 사용한다. `dict`는 내부 구조가 불명확하므로 타입 안전한 `DraftSpec`으로 통일한다.

**작업자**: 황대원(REQ-012 확장) + 신정혜(REQ-004 클래스명 변경) + 박아름(REQ-003 삭제→import)

---

### H-11. WorkflowNode vs NodeInstance 이중 정의 (REQ-004 vs REQ-012)

**제안: `NodeInstance`로 클래스명 통일, `credential_id` 추가** - 확정

```
REQ-012 NodeInstance 최종:
  instance_id: UUID                  (인스턴스 고유 식별자)
  node_id: UUID                      (NodeConfig FK)
  parameters: dict[str, Any]         (REQ-012 필드명 유지)
  credential_id: Optional[str]       (REQ-004에서 승격)
  position: Position

REQ-004: WorkflowNode 삭제, NodeInstance import
```

**근거:**
- **`node_id` 이중 의미 해소가 핵심**: REQ-004에서 `node_id`는 "이 노드 인스턴스의 고유 식별자"이고, REQ-012에서 `node_id`는 "이 인스턴스가 참조하는 노드 정의의 ID"이다. 같은 필드명이 완전히 다른 의미로 사용되면, 코드에서 `instance.node_id`가 어떤 값인지 맥락 없이는 알 수 없다. REQ-012의 `instance_id`(인스턴스 식별) + `node_id`(정의 참조) 2필드 구조가 의미를 명확히 분리한다.
- **`credential_id` 승격 이유**: REQ-002(Auth-Security)의 `CredentialInjectionService`가 노드 실행 시 자격증명을 주입하려면, 각 노드 인스턴스가 어떤 자격증명을 사용하는지 알아야 한다. 이 필드가 SSOT에 없으면 보안 서비스가 별도 매핑 테이블을 관리해야 하는 불필요한 복잡성이 생긴다.
- **`parameters` 필드명 유지 이유**: REQ-004는 `params`, REQ-012는 `parameters`를 사용한다. 축약형(`params`)은 검색 시 `parameters`와 매칭되지 않아 코드 검색을 어렵게 한다. 풀네임을 사용하는 것이 유지보수에 유리하다.

**작업자**: 황대원(REQ-012에 credential_id 추가) + 신정혜(REQ-004 WorkflowNode 삭제→import)

---

## MEDIUM 이슈 해결 제안

### M-1. DAGScheduler 명칭 혼동

**제안: `TopologicalScheduler`로 개명** - 확정

**근거:**
- REQ-007이 LangGraph StateGraph를 실행 엔진으로 채택한 상태에서, REQ-009에 "DAG"라는 이름이 남아있으면 "실행 엔진의 DAG인가, 스케줄링의 DAG인가" 혼동이 발생한다. `Topological`은 사용하는 알고리즘(Kahn's topological sort)을 직접 반영하므로 목적이 명확해진다.

**작업자**: 황대원(REQ-009)

---

### M-5. LangGraph REQ-004→REQ-007 핸드오프 미문서화

**제안: architecture 문서에 핸드오프 인터페이스 명시** - 비동기(async) 구조로 협의 완료.

```
핸드오프 흐름:
  REQ-004 SkillAgent
    → QAEvaluatorService.evaluate() → score ≥ 8 통과
    → WorkflowRepository.save(workflow) → workflow_id 반환
    
  REQ-007 ExecutionEngine
    → WorkflowRepository.get(workflow_id) → WorkflowSchema
    → 노드별 Celery 태스크 디스패치
```

**근거:**
- 현재 두 REQ의 경계가 문서로 정의되어 있지 않아, 구현 시 "QA 통과 후 누가 실행을 트리거하는가"에 대한 해석 차이가 생길 수 있다. API 엔드포인트(REQ-009)가 중간에 개입하는지, 이벤트 기반인지 명확히 해야 한다.

**작업자**: 황대원(architecture 문서 작성)

---

### M-6. SourceRef 정의 불일치 (REQ-006 vs REQ-012)

**제안: REQ-006의 `SourceRef` VO를 REQ-012에 SSOT로 승격** - 확정

```
REQ-012에 추가:
  class SourceRef(BaseModel):
      page: Optional[int]
      section: Optional[str]
      block_index: Optional[int]
      bbox: Optional[BBox]
      sheet_name: Optional[str]
      slide_number: Optional[int]

REQ-012 변경: source_ref: dict → source_ref: Optional[SourceRef]
REQ-006: 자체 SourceRef 삭제, import
```

**근거:**
- **`dict` 타입의 위험**: `dict`는 키가 무엇이고 값이 어떤 타입인지 런타임 전까지 알 수 없다. `{"page": "세번째"}` 같은 잘못된 값이 들어와도 Pydantic이 잡아주지 못한다.
- **REQ-006이 이미 상세 정의를 완료함**: REQ-006 담당자(김진형)가 파서 도메인 전문가로서 필요한 참조 정보(페이지, 섹션, bbox 등)를 이미 정의해 둔 상태다. 이 작업을 REQ-012에서 다시 할 이유가 없다.
- **H-8과 동시 해결**: ContentBlock의 `source_ref`를 VO로 바꾸면 H-8의 `dict` vs VO 불일치도 함께 해소된다.

**작업자**: 황대원(REQ-012) + 김진형(REQ-006 import 전환)

---

### M-7. Chunk.importance_score 크로스 모듈 의존성 (REQ-006 → REQ-004)

**제안: 데이터 흐름 문서화 + Optional 유지** - IntentAnalyzer에서 importance_score 연산하는 것으로 확정

```
파이프라인:
  REQ-006 Parser → Chunk(importance_score=None)
    → REQ-004 AI Agent (IntentAnalyzer 또는 QAEvaluator)
    → Chunk(importance_score=0.85)
```

**근거:**
- **왜 REQ-006에 이 필드가 있는가**: 파서는 청크를 생성하지만 중요도는 판단할 수 없다 (도메인 지식이 없으므로). AI Agent가 LLM을 통해 중요도를 채워넣는 구조인데, 이 흐름이 어디에도 문서화되어 있지 않으면 "누가 None을 채우는가?"가 불명확해진다.
- **코드 변경 없이 문서화로 해결**: 필드 자체는 `Optional[float]`로 적절하게 선언되어 있다. 실제 필요한 것은 "어느 시점에 누가 채우는가"를 architecture 문서에 명시하는 것이다.

**작업자**: 신정혜(REQ-004에서 계산 시점 확인) + 황대원(architecture 문서 반영)

---

### M-8. BaseTool.risk_level vs NodeConfig.risk_level 타입 불일치 (REQ-005 vs REQ-012)

**제안: REQ-012에 공유 `RiskLevel` Enum 정의, 양쪽 import** - 확정

```
REQ-012에 추가:
  class RiskLevel(str, Enum):
      LOW = "Low"
      MEDIUM = "Medium"
      HIGH = "High"
      RESTRICTED = "Restricted"

REQ-012 NodeConfig: risk_level: Literal[…] → risk_level: RiskLevel
REQ-005 BaseTool: risk_level: RiskLevel (import)
```

**근거:**
- **`str, Enum` 이중 상속 이유**: `str`을 상속하면 JSON 직렬화 시 자동으로 문자열로 변환되어, 기존에 Literal을 사용하던 코드와 하위호환이 유지된다. `RiskLevel.LOW == "Low"`가 True가 되므로 기존 비교 로직도 깨지지 않는다.
- **Enum을 REQ-012에 두는 이유**: risk_level은 노드 정의(REQ-012 NodeConfig)와 도구 정의(REQ-005 BaseTool) 양쪽에서 사용하는 공유 타입이다. REQ-003의 `ToolToNodeWrapper`가 BaseTool→BaseNode 변환 시 risk_level 매핑이 필요한데, 양쪽이 같은 Enum을 사용하면 변환 로직이 불필요해진다.

**작업자**: 황대원(REQ-012 Enum 추가) + 햄햄(REQ-005 import)

---

### M-9. RuntimeValidator vs QAEvaluatorService 역할 경계 (REQ-005 vs REQ-004)

**제안: 코드 변경 없이, 각 클래스에 역할 범위 주석 1줄 추가** - 확정

```
REQ-005 RuntimeValidator:   "도구 실행 시점 I/O 스키마 검증 (per-tool, 데이터 타입 검증)"
REQ-004 QAEvaluatorService: "워크플로우 초안 품질 평가 (LLM-as-a-Judge, 의미적 검증)"
```

**근거:**
- 두 클래스는 검증 대상(도구 I/O vs 워크플로우), 검증 방식(스키마 vs LLM), 실행 시점(런타임 vs 설계 시)이 모두 다르므로 실제 충돌은 없다. 다만 팀원이 코드를 처음 볼 때 "Validator와 Evaluator의 차이가 뭐지?"라는 의문이 생길 수 있으므로, 주석으로 경계를 명시하면 충분하다.
- 클래스명 변경은 불필요하다. `Validator`(규칙 기반 통과/불통과)와 `Evaluator`(점수 기반 품질 평가)는 이미 의미가 구별된다.

**작업자**: 각 담당자 (선택사항, 필수 아님)

---

### M-10. MemoryEntry vs AgentMemoryModel 필드 매핑 불일치 (REQ-004 vs REQ-001)

**제안: 필드명 통일 + 매핑 관계 명시** - 확정

```
필드명 통일:
  REQ-001 owner_user_id  →  user_id      (REQ-004 기준)
  REQ-001 memory_kind    →  memory_type   (REQ-004 기준)

ORM 전용 필드 (도메인 모델에 불포함):
  confidence, usage_count, last_used_at   →  REQ-001에만 유지

REQ-004 MemoryEntry에 추가:
  source_session_id: Optional[UUID]       (디버깅 추적용)
```

**근거:**
- **도메인 모델 ≠ ORM 모델**: REQ-004 MemoryEntry는 비즈니스 로직이 사용하는 도메인 모델이고, REQ-001 AgentMemoryModel은 DB 테이블을 1:1 매핑하는 ORM 모델이다. 두 모델이 동일할 필요는 없지만, **같은 개념을 다른 이름으로 부르는 것**(`user_id` vs `owner_user_id`)은 혼란의 원인이다.
- **ORM 전용 필드를 도메인에 넣지 않는 이유**: `usage_count`, `last_used_at`은 DB 쿼리 최적화(자주 사용되는 메모리 우선 조회)를 위한 필드다. 비즈니스 로직에서 이 값을 직접 다룰 일은 없으므로, 도메인 모델을 비대하게 만들 필요가 없다.
- **`source_session_id`를 REQ-004에 추가하는 이유**: "이 메모리가 어떤 세션에서 생성되었는가"는 디버깅과 사용자 설명에 유용하다 ("이 메모리는 5월 3일 대화에서 학습된 것입니다"). 도메인 레벨에서도 의미 있는 정보이므로 Optional로 추가한다.

**작업자**: 황대원(REQ-001 필드명 수정) + 신정혜(REQ-004 source_session_id 추가)

---

### M-11. NodeRegistry vs NodeDefinitionRepository 이중 정의 (REQ-004 vs REQ-003)

**제안: REQ-004 NodeRegistry가 REQ-003 ABC를 주입받는 어댑터 구조** - 확정

```
REQ-003: NodeDefinitionRepository (ABC) — 변경 없음
REQ-004: NodeRegistry에 의존성 주입

class NodeRegistry:
    def __init__(self, repo: NodeDefinitionRepository):
        self._repo = repo
        self._embeddings = pgvectorIndex

    def search(self, query: str, k: int = 10) -> list[NodeDef]:
        return self._repo.search_by_embedding(query, k)

    def get_schema(self, node_type: str) -> dict:
        node = self._repo.get_by_id(node_type)
        return node.to_schema_dict()
```

**근거:**
- **ABC를 없애지 않는 이유**: REQ-003의 `NodeDefinitionRepository`는 CRUD 풀셋(upsert, list_all, get_by_id, search_by_embedding)을 정의하는 범용 ABC다. 관리 도구(노드 정의 등록/삭제)와 AI Agent(노드 검색) 모두 이 ABC를 통해 접근해야 하므로, 삭제하면 범용성을 잃는다.
- **NodeRegistry를 없애지 않는 이유**: AI Agent(REQ-004)는 전체 CRUD가 아니라 "검색"과 "스키마 조회"만 필요하다. NodeRegistry는 이 좁은 인터페이스를 제공하는 Facade로, AI Agent가 불필요한 CRUD 메서드에 의존하지 않게 해준다 (인터페이스 분리 원칙).
- **어댑터 패턴 선택 이유**: NodeRegistry가 ABC를 주입받으면, 테스트 시 Mock ABC를 주입하여 DB 없이 테스트할 수 있다. 또한 ABC 구현체가 바뀌어도(예: PostgreSQL → Redis 캐시) NodeRegistry 코드는 변경할 필요가 없다.

**작업자**: 신정혜(REQ-004 NodeRegistry에 의존성 주입 표기)

---

## LOW 이슈 해결 제안

### L-1. 파일명 컨벤션 통일

**제안: `REQ-XXX-모듈명.drawio` 형식 통일** - 해결됨.

| 현재 | 변경 후 |
|------|---------|
| `REQ-004-AI agent.drawio` | `REQ-004-AI-Agent.drawio` |
| `REQ-005_AI Agent Tool.drawio` | `REQ-005-Toolset.drawio` |
| `REQ-006_Data_Class.drawio` 외 2개 | `REQ-006-DocParser.drawio` (통합) |
| `REQ-002.drawio` | `REQ-002-Auth-Security.drawio` |
| `REQ-003.drawio` | `REQ-003-Nodes-Graph.drawio` |

**근거:**
- 공백과 언더스코어가 혼재하면 CLI에서 파일 경로를 다룰 때 이스케이프 문제가 발생한다. 하이픈은 이스케이프 없이 사용할 수 있는 가장 안전한 구분자다.

**작업자**: 각 담당자

---

### L-2. REQ-006 파일 3개 분리

**제안: draw.io 멀티탭으로 단일 파일 통합** - 현재 유지.

**근거:** 다른 REQ는 모두 단일 파일이므로 일관성 유지. draw.io는 탭 기능을 지원하므로 Data_Class, Parser_Engine, Service_Layer를 탭으로 분리하면 파일 수를 줄이면서도 구조적 분리를 유지할 수 있다.

**작업자**: 김진형(REQ-006)

---

### L-3. 색상 범례

현재 상태 유지. REQ-002, 003의 자체 범례 방식이 적절함. 팀 전체 색상 통일은 ROI가 낮다. - 확정

---

## 작업자별 요약

### 황대원 (REQ-001, 009, 012)

| 대상 | 작업 내용 | 관련 이슈 |
|------|----------|----------|
| REQ-012 AgentState | session_id, user_id, turn_count, execution_status 추가, mode→Enum, AgentMode/ExecutionStatus Enum 추가 | H-9 |
| REQ-012 WorkflowSchema | description, version, sha256, created_via_session_id 추가, scope 소문자 통일 | H-10 |
| REQ-012 NodeInstance | credential_id 추가 | H-11 |
| REQ-012 DocumentBlock | workflow_id, user_id, parser→ParserMeta 추가 | H-6 |
| REQ-012 FileMeta | page_count, unit_type, created_at, author, sheet_meta 추가 | H-7 |
| REQ-012 ContentBlock | table, page, section_title, bbox 추가, source_ref→SourceRef VO, block_type에 "code" 추가 | H-8 |
| REQ-012 SourceRef | 신규 VO 클래스 추가 | M-6 |
| REQ-012 RiskLevel | 신규 Enum 추가, NodeConfig Literal→Enum 교체 | M-8 |
| REQ-001 Repositories | 메서드명·시그니처를 REQ-002 ABC 기준으로 통일 | H-3 |
| REQ-001 Cipher | 자체 EncryptionStrategy 삭제, REQ-002 cipher DI 전환 | H-2 |
| REQ-001 AgentMemoryModel | owner_user_id→user_id, memory_kind→memory_type 필드명 수정 | M-10 |
| REQ-009 | DAGScheduler→TopologicalScheduler 개명 | M-1 |
| architecture 문서 | REQ-004→REQ-007 핸드오프, importance_score 흐름 문서화 | M-5, M-7 |

### 신정혜 (REQ-004)

| 작업 내용 | 관련 이슈 |
|----------|----------|
| AgentState → REQ-012 import, intent_result 필드 추가 | H-9 |
| WorkflowDraft → WorkflowSchema 클래스명 변경, import | H-10 |
| WorkflowNode 삭제 → NodeInstance import | H-11 |
| NodeDef → NodeConfig 타입명 통일 | H-9 |
| MemoryEntry에 source_session_id 추가 | M-10 |
| NodeRegistry에 NodeDefinitionRepository 의존성 주입 표기 | M-11 |
| importance_score 계산 시점·로직 확인 | M-7 |

### 박아름 (REQ-002, REQ-003)

| 작업 내용 | 관련 이슈 |
|----------|----------|
| REQ-003 WorkflowSchema/NodeInstance/Edge 자체 정의 삭제 → REQ-012 import | H-1, H-10 |
| REQ-003 NodeDefinition에 risk_level, required_connections, service_type 필드 존재 명시 | H-4 |
| REQ-002 cipher 시그니처 bytes→bytes 통일 | H-2 |
| REQ-003 draft_spec: dict → DraftSpec 타입 변경 | H-10 |

### 김진형 (REQ-006)

| 작업 내용 | 관련 이슈 |
|----------|----------|
| DocumentBlock 자체 정의 삭제 → REQ-012 import | H-6 |
| FileMeta에 mime_type 추가 후 자체 정의 삭제 → REQ-012 import | H-7 |
| Block → ContentBlock import | H-8 |
| SourceRef 자체 정의 삭제 → REQ-012 import | M-6 |
| 3개 파일 → 단일 파일 멀티탭 통합 (선택) | L-2 |

### 햄햄 (REQ-005)

| 작업 내용 | 관련 이슈 |
|----------|----------|
| RiskLevel → REQ-012 Enum import | M-8 |
| 파일명 컨벤션 수정 (선택) | L-1 |

---

## 논의 필요 사항

아래 항목은 제안자(황대원)의 판단만으로 결정하기 어려우므로 팀 논의가 필요하다.

| # | 질문 | 관련 이슈 | 결정 필요 참석자 |
|---|------|----------|----------------|
| 1 | AgentState에 `turn_count` 상한을 25로 고정할 것인가, 설정 가능하게 할 것인가? | H-9 | 신정혜, 황대원 |
| 2 | `sha256` 무결성 검증을 어느 시점에 수행할 것인가? (저장 시? 실행 전? 양쪽?) | H-10 | 신정혜, 황대원 |
| 3 | REQ-004→REQ-007 핸드오프는 동기(API 호출)인가, 비동기(이벤트/큐)인가? | M-5 | 신정혜, 황대원 |
| 4 | `importance_score`를 계산하는 주체가 IntentAnalyzer인가 QAEvaluator인가? | M-7 | 신정혜, 김진형 |
| 5 | REQ-001 ORM의 `confidence`, `usage_count` 필드를 도메인 모델에도 노출할 필요가 있는가? | M-10 | 신정혜, 황대원 |
| 6 | MemoryEntry의 `user_id` 타입을 `str`(SHA256 해시)로 할 것인가 `UUID`로 할 것인가? REQ-001 ORM은 `UUID`를 사용 중. | M-10 | 신정혜, 황대원 |
