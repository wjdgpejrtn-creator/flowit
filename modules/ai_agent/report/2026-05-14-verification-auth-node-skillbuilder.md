# 조장 검증 요청 결과 — Auth / Node / Skill Builder 3 영역

**검증 일자**: 2026-05-14 (목)
**검증자**: 박아름 (REQ-002 Auth · REQ-003 Nodes-Graph · REQ-004 Skills Builder 담당)
**요청자**: 황대원 (조장)
**검증 방식**: 각 영역 브랜치/코드에 직접 들어가서 파일경로:라인범위 인용 기반 사실 확인

---

## 1. Auth — ⚠️ 부분 구현 (백엔드 ✅ / API+Frontend ❌)

**조장 질문**: "노드에 만약 해당 슬랙/구글 등이 인증이 안되어있으면 auth 영역에서 로그인 하게끔 만들어져 있는가?"

### 1.1 ✅ 백엔드 구현 완료 (박아름 영역 `modules/auth`)

| 항목                                    | 위치                                                                                                        | 상태 |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ---- |
| OAuth credential 저장/암호화            | `modules/auth/adapters/oauth/google_oauth_client.py` + AES-256-GCM (`adapters/cipher/aes_gcm.py:10-30`) | ✅   |
| OAuth 코드 교환 + DB 저장 + JWT 발급    | `application/use_cases/authenticate_use_case.py:31-58`                                                    | ✅   |
| 워크플로우 검증 시 필수 connection 체크 | `nodes_graph/domain/services/graph_validator.py:126-139` → `E_MISSING_CONNECTION`                      | ✅   |
| 노드 실행 시 credential 주입            | `auth/domain/services/credential_injection_service.py:23-42` (OAuth 연결 활성 검증 + AES-GCM 복호화)      | ✅   |
| RESTRICTED 등급 추가 권한 검증          | `credential_injection_service.py:28-29` (`AuthorizationError` raise)                                    | ✅   |
| Refresh token rotation                  | `application/use_cases/refresh_token_use_case.py` (폐기된 세션 → `E-AUTH-006`)                         | ✅   |
| 6차원 권한 모델                         | `domain/services/permission_resolver.py:7-33` (Admin/User 분기 + risk_ceiling)                            | ✅   |

### 1.2 ❌ API + Frontend 미구현 (Critical, REQ-009/010 조장 영역)

| 누락 항목                               | 영향                                                                                                   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **API 라우터 부재**               | `services/api_server/app/main.py`는 `/health`만 구현. `/auth/authorize`, `/auth/callback` 없음 |
| **SSE 에러 이벤트 부재**          | `E_MISSING_CONNECTION` 발생해도 클라이언트에 전달하는 체계 없음                                      |
| **Frontend OAuth flow 없음**      | 사용자 redirect → Google 로그인 페이지 유도 미구현                                                    |
| **토큰 만료 → 재인증 유도 흐름** | JWT 401 응답은 처리되지만 사용자에게 보여줄 OAuth URL handler 없음                                     |

### 1.3 e2e 시나리오 — 미인증 사용자가 슬랙 노드 실행 시도

| 단계                                               | 상태      | 구현 위치                              |
| -------------------------------------------------- | --------- | -------------------------------------- |
| ① 사용자 워크플로우 실행 요청                     | ⚠️ 부분 | API 라우터 미구현                      |
| ② Credential 검증 실패 (`E_MISSING_CONNECTION`) | ✅        | `graph_validator.py:132`             |
| ③ SSE 에러 이벤트 발행                            | ❌ 미구현 | —                                     |
| ④ 클라이언트 → OAuth 로그인 유도                 | ❌ 미구현 | frontend URL handler 없음              |
| ⑤ 사용자 Google OAuth 동의                        | ✅        | `authenticate_use_case.py:31`        |
| ⑥ Token 저장 및 JWT 발급                          | ✅        | `authenticate_use_case.py:42-58`     |
| ⑦ 재시도 → 슬랙 노드 정상 실행                   | ✅        | `credential_injection_service.py:23` |

### 1.4 종합 평가 — Auth 영역

- **박아름 영역(`modules/auth`) 완성도**: ✅ **100% 완성**. 모든 도메인 서비스 + 어댑터 + use case + 권한 평가 구현 완료. 단위 테스트 12건 통과.
- **e2e 흐름 완성도**: ⚠️ **70%**. 백엔드는 완성됐으나 API 엔드포인트 + Frontend redirect 미구현이라 사용자가 직접 OAuth 로그인 유도되는 흐름은 작동 안 함.
- **차단 원인**: 박아름 영역 외부 (REQ-009 api_server, REQ-010 frontend — 조장 영역)
- **권고**: REQ-009 완성 시 `/auth/callback` 라우터 추가, Frontend에서 `E_MISSING_CONNECTION` 수신 시 Google OAuth URL로 redirect 처리 필요. 백엔드는 이미 준비됨.

---

## 2. Node — ✅ 자세히 고려됨 (3단계 중복 처리)

**조장 질문**:

1. node_id = primary key 로 되어있는지?
2. 중복 노드를 document(코드) / adapter(DB) 두 곳에서 잡아내면서 자세히 고려해서 만들었는지?
3. node 쪽도 e2e 실행해봤는지?

### 2.1 DB 스키마 — PRIMARY KEY + UNIQUE 제약

**파일**: `database/schemas/009_node_definitions.sql:6-8`

- ✅ `node_id` → **PRIMARY KEY** (UUID, DEFAULT `gen_random_uuid()`)
- ✅ `node_type` → **UNIQUE 제약** (VARCHAR 100)

**ORM 매핑**: `modules/storage/orm/node_definition_model.py:17-18`

- SQLAlchemy ORM에서 `node_type`에 `unique=True` 명시적 지정 (DB 제약과 정합)

→ **결론**: node_id가 PK이며, node_type이 UNIQUE 제약으로 보호. 같은 타입의 중복 삽입 불가.

### 2.2 중복 검출 3단계

| 단계                           | 위치                                                                                | 알고리즘                                         | 검출 대상                                     |
| ------------------------------ | ----------------------------------------------------------------------------------- | ------------------------------------------------ | --------------------------------------------- |
| **① Domain (Document)** | `nodes_graph/domain/services/graph_validator.py:46-61` (`_check_duplicate_ids`) | Set 기반 O(1) 스캔, ErrorCode `E_DUPLICATE_ID` | **워크플로우 내 instance_id 중복**      |
| **② Adapter (DB)**      | `storage/repositories/pg_node_definition_repository.py:21-25` (`upsert`)        | SQLAlchemy `session.merge()` + DB UNIQUE 제약  | **카탈로그의 node_id / node_type 중복** |
| **③ 운영 (Cleanup)**    | `scripts/bootstrap_node_definitions.py:161-185` (`_cleanup_placeholder`)        | 박아름 카탈로그 set 외 모두 DELETE               | **외래 시드 / placeholder row**         |

### 2.3 결정론적 ID — uuid5 namespace 패턴

**파일**: `modules/nodes_graph/domain/catalog/_catalog_ns.py`

```python
_CATALOG_NS = uuid5(NAMESPACE_DNS, "workflow-automation.catalog")
```

- 각 node_type마다 `uuid5(_CATALOG_NS, node_type)` 호출 (예: `anthropic_chat.py:3`)
- 같은 node_type은 항상 같은 node_id 생성 → **결정론적 멱등성** 보장
- `session.merge()` 패턴과 결합돼 부분 실패 후 재실행 안전

### 2.4 is_mvp 구분 — 카탈로그 vs SkillNode

- ✅ `database/schemas/009_node_definitions.sql:23`: `is_mvp BOOLEAN DEFAULT FALSE`
- ✅ `bootstrap_node_definitions.py:13`: SkillNode는 `is_mvp=False` 명시 등록
- ✅ `pg_node_definition_repository.py:29-30`: `list_all(mvp_only=True)` 필터 구현
- 중복 처리 기준: **node_type UNIQUE 하나로 통합 관리** (is_mvp 값과 무관)

### 2.5 e2e 검증 — 2026-05-13 박아름 직접 실행

| 항목                      | 결과                                                                                                 |
| ------------------------- | ---------------------------------------------------------------------------------------------------- |
| DB 등록 row               | **85개** (카탈로그 55 + SkillNode 30)                                                          |
| Embedding                 | **100% NOT NULL** (BGE-M3 768d, 가이드 §1.3 함정 회피)                                        |
| BGE-M3 자연어 검색 정확도 | **top-5 = 77.8%** (10 쿼리 × top-5 = 14/18)                                                   |
| 대표 매칭                 | `slack_post_message`, `ecommerce_refund_approval`, `http_request`, `csv_parse` 등 top-1 정확 |
| 동의어/유의어 동시 매칭   | `slack_post_message` + `slack_notify`, `http_request` + `rest_api` + `http_request_tool`   |
| 한국어 다국어 처리        | 정상 (BGE-M3 다국어 모델 특성)                                                                       |

### 2.6 종합 평가 — Node 영역

| 항목         | 결과 | 근거                                |
| ------------ | ---- | ----------------------------------- |
| node_id PK   | ✅   | `009_node_definitions.sql:7`      |
| UNIQUE 제약  | ✅   | `node_type VARCHAR(100) UNIQUE`   |
| Domain 검출  | ✅   | `graph_validator.py:46-61`        |
| Adapter 검출 | ✅   | `session.merge()` + DB UNIQUE     |
| 결정론적 ID  | ✅   | `uuid5(_CATALOG_NS, node_type)`   |
| Cleanup 운영 | ✅   | `bootstrap --cleanup-placeholder` |
| is_mvp 구분  | ✅   | 필터링 + node_type 통합             |
| e2e 검증     | ✅   | 5/13 박아름 직접 (77.8% top-5)      |

→ **결론**: **document(GraphValidator instance_id) + adapter(DB UNIQUE/merge) + 운영(cleanup) 3단계 모두 자세히 구현**. 결정론적 uuid5로 멱등성 보장. e2e 검증 완료.

---

## 3. Skill Builder — ✅ 책임 경계 확정 (옵션 A 채택, 5/14 박아름 결정)

**조장 질문 (원문)**:

- "지침서 형태의 하네스만 하는건지"
- "지침서 바탕으로 워크플로우를 고정한다."
- "초안을 짤때 초안을 짜는 기준 자체를 하네스 구조로 해서"
- "워크플로우를 어디까지 짜는건지 결정하기"
- "자연어 툴이나 노드도 검색을 하지만 마켓플레이스에 있는 스킬을 검색을 함"
- "지침서만 줄건지 / 지침서에 따른 워크플로우까지 할건지 클로드랑 정하기"

### 3.1 현재 구현 상태 (사실 기반)

**3개 Use Case 모두 동일 패턴** (`modules/ai_agent/application/agents/skills_builder/`):

| Use Case                             | 입력                                   | 처리                                                                      | 출력                                            |
| ------------------------------------ | -------------------------------------- | ------------------------------------------------------------------------- | ----------------------------------------------- |
| `BuildFromSOPUseCase`              | `DocumentBlock`                      | LLM `generate_structured` (Gemma 4) → `_ExtractedSkillNodeList` 검증 | SkillNode → NodeDefinition →`repo.upsert()` |
| `BuildFromIndustryDefaultUseCase`  | `industry_code` (예: ecommerce)      | seed JSON 로드 → Pydantic 검증                                           | SkillNode → NodeDefinition →`repo.upsert()` |
| `BuildFromFunctionalDomainUseCase` | `domain_code` (예: customer_support) | seed JSON 로드 → Pydantic 검증                                           | SkillNode → NodeDefinition →`repo.upsert()` |

**ResultFrame.payload 구조**:

- `upserted_count`, `failed_count`, `node_types`, `failed_node_types`, `source_type`, `user_id`
- **WorkflowSchema / edge / 연결 정보 없음**

**LLM 프롬프트 강제 스키마** (`build_from_sop_use_case.py:90-113` `_ExtractedSkillNode`):

- 필드: `node_type`, `name`, `description`, `category`, `risk_level`, `inputs`, `outputs`, `required_connections`, `service_type`
- **개별 노드 정의만 추출** — edge / 연결 / 워크플로우 구조 정보 없음

**코드 전체 grep 결과**:

- `WorkflowSchema(` 생성 로직 → **skills_builder 전체에서 0건**
- `Edge(` 생성 → **0건**
- 즉 **워크플로우 청사진 생성 코드 자체가 없음**

### 3.2 REQ-004 spec과의 정합성

**`docs/specs/REQ-004-ai-agent.md` §2.2 (라인 127~131)**:

```
출력: AsyncGenerator[SSEFrame]
→ SSEFrame은 AgentNodeFrame/ErrorFrame/ResultFrame 포함 (프로토콜만 정의)
→ WorkflowSchema 생성 명시 없음
→ "노드 정의 카탈로그 등록"이 Skills Builder 책임으로 명시
```

→ **현재 구현은 spec 그대로**. SkillNode 추출 + 카탈로그 등록만 책임.

### 3.3 책임 경계 (현재 정의)

```
Skills Builder (박아름)        →  SkillNode 카탈로그 공급 (DB upsert)
Workflow Composer (신정혜)     →  workflow draft → validate → qa (사용자 채팅 기반)
nodes_graph SearchUseCase      →  자연어 → 노드/스킬 BGE-M3 검색 (is_mvp=False 포함)
```

**마켓플레이스 스킬 검색**:

- ✅ **`nodes_graph.application.use_cases.SearchNodesUseCase`** 가 담당
- ✅ is_mvp=False (SkillNode) 포함해서 BGE-M3 코사인 유사도 검색
- ❌ **skills_builder 영역에는 검색 endpoint 없음** (skill 생성 전용)

### 3.4 조장 질문별 답변

| 조장 질문                          | 답변                                                 | 근거                                         |
| ---------------------------------- | ---------------------------------------------------- | -------------------------------------------- |
| "지침서만 하는건지"                | ✅**예. SkillNode 추출/정의만**                | LLM 프롬프트 + ResultFrame payload 구조      |
| "워크플로우까지 고정하는가"        | ❌**아니오. SkillNode 카탈로그만**             | `WorkflowSchema(` 생성 코드 0건            |
| "초안 기준을 하네스 구조로 하는가" | ✅ 예                                                | `_ExtractedSkillNode` Pydantic 스키마 강제 |
| "마켓플레이스 스킬 검색"           | **skills_builder 영역 아님**                   | `nodes_graph.SearchNodesUseCase` 담당      |
| "지침서만 줄건지/워크플로우까지"   | **현재 = 지침서(SkillNode)만**, spec 준수 상태 | REQ-004 §2.2                                |

### 3.5 ✅ 박아름 5/14 결정 — 옵션 A 채택 (Skills Builder = 스킬 생성 전용)

**박아름 본인 결정 (2026-05-14)**:

> **Skills Builder = 스킬 생성 전용**
>
> 세부적으로 풀면:
> 1. 입력 받음 (SOP 문서 / 산업 코드 / 직무 코드)
> 2. LLM 또는 시드로 SkillNode 추출
> 3. DB에 upsert
> 4. 끝

#### 명시적으로 안 하는 것 (책임 외)
- ❌ 워크플로우(WorkflowSchema) 생성 — Composer (신정혜) 영역
- ❌ Edge / 노드 연결 정보 추출 — LLM 프롬프트가 개별 SkillNode만 추출
- ❌ 사용자 채팅·확인·등록 응답 처리 — Main Orchestrator (신정혜) 영역
- ❌ 마켓플레이스 검색 endpoint — `nodes_graph.SearchNodesUseCase` 담당

#### 옵션 A 채택 근거
- **REQ-004 spec §2.2 그대로 정합** — 별도 spec 변경 불필요
- **책임 경계 명확** — Composer/Orchestrator와 중복 없음
- **모듈 간 결합도 낮음** — Skills Builder가 SkillNode만 책임지면 됨
- **현재 구현 그대로 유지** — 추가 코드 작업 0건

#### 옵션 B는 Sprint 4 이연 (현재 결정 아님)
- Skills Builder가 WorkflowSchema 청사진까지 만드는 확장은 Sprint 4 로드맵 검토
- LLM 프롬프트에 edge 추출 추가 + Composer와 책임 재정의 필요
- 현재(Sprint 3)는 옵션 A 유지

→ **결정 완료. 박아름 영역 추가 작업 0건. 메모리 박힘**: `project_skills_builder_customization_v2.md` 5/14 갱신 섹션.

---

## 4. 카탈로그 AI 노드 + LLM 호출 흐름 — ⚠️ 메타데이터만 / 실행 코드 미구현 (실행 wiring 차단)

**박아름 추가 검증 질문 (자체 점검)**:

1. 카탈로그 55개 중에 워크플로우 실행 단계에서 LLM 호출하는 노드가 활성 상태로 등록돼 있는가?
2. 그 노드가 내부적으로 어떤 LLM(신정혜 Gemma 4 vs 외부 Anthropic/OpenAI)을 호출하는가?

### 4.1 AI 카테고리 노드 — `anthropic_chat` 1개만

**전체 카탈로그(`domain/catalog/` + `adapters/catalog/`) 탐색 결과**: AI 카테고리(`category="ai"`) 노드 **1건**.

| 필드                           | 값                            | 위치                                                                       |
| ------------------------------ | ----------------------------- | -------------------------------------------------------------------------- |
| **node_type**            | `anthropic_chat`            | `modules/nodes_graph/adapters/catalog/external/anthropic_chat.py:40`     |
| **name**                 | "Anthropic Chat"              | 같은 파일                                                                  |
| **category**             | `"ai"`                      | 같은 파일                                                                  |
| **is_mvp**               | `True` ✅ **활성**    | 비활성 보류 5종(Outlook/Teams/OneDrive/OpenAI Chat/Notion)에 포함되지 않음 |
| **required_connections** | `["anthropic"]`             | 외부 Anthropic API 자격증명 필요                                           |
| **service_type**         | `"anthropic"`               | —                                                                         |
| **risk_level**           | `MEDIUM`                    | —                                                                         |
| NodeDefinition 정의 위치       | `anthropic_chat.py:100-103` | —                                                                         |

→ 비활성 보류 5종에 포함되지 않은 활성 AI 노드. MVP 대상.

### 4.2 ⚠️ 실행 코드 = `NotImplementedError`

**`modules/nodes_graph/adapters/catalog/external/anthropic_chat.py:50-54`**:

```python
async def process(self, input: AnthropicChatInput) -> AnthropicChatOutput:
    raise NotImplementedError(
        "Anthropic API 호출은 REQ-005 toolset connector를 통해 처리. "
        "API key 주입은 REQ-002 CredentialInjectionService 담당."
    )
```

→ **노드 정의 파일의 `process()` 메서드는 명시적으로 `NotImplementedError`**. 책임을 REQ-005 toolset (햄햄 영역) + REQ-002 credential injection (박아름 영역)에 위임.

### 4.3 LLM 클라이언트 추적 — 코드베이스 전체 grep 결과

| 클라이언트                                    | import 건수                | 의미                                                                   |
| --------------------------------------------- | -------------------------- | ---------------------------------------------------------------------- |
| `import anthropic` (Anthropic SDK)          | **0건**              | 외부 Anthropic Claude API 직접 호출 코드 0건                           |
| `import openai` (OpenAI SDK)                | **0건**              | 외부 OpenAI API 직접 호출 코드 0건                                     |
| `ModalLLMAdapter` (신정혜 llm-base Gemma 4) | 박아름 ai_agent에서만 사용 | anthropic_chat 노드와**연결 0건** — ai_agent 모듈이 별도 도메인 |

### 4.4 Workflow 실행 시점 — 어떻게 작동하는가

**실행 흐름 추적**:

1. workflow에 `anthropic_chat` 노드 포함 → execution_engine 실행
2. `services/execution_engine/src/adapters/toolset_executor.py:24-53` — `ToolsetExecutor`가 `tool_name`(node_type) 기반 `execute_tool()` 콜백 호출
3. `services/execution_engine/src/dependencies/container.py:144-145` — **실제 `execute_tool` 구현이 없음** (noop executor / NotImplementedError)

→ **워크플로우에 `anthropic_chat` 노드가 들어가면 실행 시점에 무조건 NotImplementedError 발생.**

### 4.5 책임 영역 분리

| 영역                                    | 책임                                                                                  | 현재 상태                                                |
| --------------------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| **박아름 REQ-003 nodes_graph**    | NodeDefinition 메타데이터 정의 (node_type, schema, risk_level, required_connections)  | ✅ 완성                                                  |
| **박아름 REQ-002 auth**           | CredentialInjectionService로 Anthropic API key 주입                                   | ✅ 완성 (anthropic credential 등록되어 있으면 주입 가능) |
| **햄햄 REQ-005 toolset**          | Anthropic API 호출 connector 구현 (`SecureConnectorAdapter` 또는 별도 tool adapter) | ❓ 미확인 (별도 검증 필요)                               |
| **조장 REQ-007 execution_engine** | `ToolsetExecutor.execute_tool` 실제 구현 (toolset connector 호출 wiring)            | ❌**미완성** (container.py 144~145 noop)           |

### 4.6 종합 평가 — 카탈로그 AI 노드 영역

| 항목                          | 결과                                        |
| ----------------------------- | ------------------------------------------- |
| AI 카테고리 노드 정의         | ✅`anthropic_chat` 1건 활성 (is_mvp=True) |
| 실행 코드 (process 메서드)    | ❌**NotImplementedError**             |
| Anthropic SDK 직접 호출       | ❌ 0건                                      |
| OpenAI SDK 직접 호출          | ❌ 0건                                      |
| Modal Gemma 4 (llm-base) 연결 | ❌**아님** — ai_agent 별도 도메인    |
| ToolsetExecutor wiring        | ❌**미완료** (noop)                   |

→ **결론**: 박아름 영역(REQ-003 nodes_graph)은 **메타데이터 레벨에서 완성**됐으나, 실제 실행 wiring(REQ-005 toolset connector + REQ-007 execution_engine `execute_tool`)은 **미완성**. 현재 워크플로우에 `anthropic_chat` 노드가 포함되면 실행 시점에 실패.

### 4.7 박아름이 조장에게 보고할 핵심 사실

> **워크플로우가 LLM 호출 시 사용할 노드는 `anthropic_chat` 1개**(외부 Anthropic Claude API 가정). 그러나:
>
> - `process()` 메서드가 `NotImplementedError`로 명시적 위임 상태
> - Anthropic / OpenAI SDK 호출 코드 0건 (코드베이스 전체)
> - 신정혜 Modal Gemma 4 (llm-base)와도 연결 없음 (ai_agent 별도 도메인)
> - REQ-005 toolset connector + REQ-007 `ToolsetExecutor.execute_tool` 구현이 선결돼야 워크플로우 실행 시 LLM 노드가 작동함
> - 박아름 영역(REQ-003 메타데이터 + REQ-002 credential 주입)은 준비됨

---

## 5. anthropic_chat 노드 역할 — 범용 LLM wrapper (문서 작성/요약/보고서는 prompt에 의존)

**박아름 추가 질문**:

- "anthropic_chat이 문서를 작성하는 노드인가?"
- "문서 작성(요약, 보고서 작성)은 누가 하는가?"

### 5.1 anthropic_chat = "범용 LLM 호출" wrapper

**`modules/nodes_graph/adapters/catalog/external/anthropic_chat.py:18-27`** input_schema:

```python
@dataclass
class AnthropicChatInput:
    model: str                              # claude-opus-4-7 / sonnet-4-6 / haiku-4-5
    messages: list[dict[str, Any]]          # [{"role": "user", "content": "..."}]
    max_tokens: int = 1024
    system: str | None = None               # system prompt
    temperature: float = 1.0
    top_p: float = 1.0
    stop_sequences: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
```

**description (라인 101)**: "Anthropic Messages API 호출 (Claude opus/sonnet/haiku). API key 자격증명 필요"

→ **Anthropic Claude API의 Messages 엔드포인트 wrapper 그 자체**. 노드 자체에는 "문서 작성", "요약", "보고서" 같은 도메인 의미가 **없음**. 무엇이든 prompt만 잘 짜면 요약·보고서·이메일·분류·번역·코딩 모두 가능.

### 5.2 카탈로그에 "요약 전용" "보고서 작성 전용" 노드 — 0건

**카탈로그 55개 grep 결과**:

- `summarize` / `summary` / `summarise` — **0건**
- `generate_text` / `report_generate` / `document_generate` — **0건**
- `요약` / `보고서` / `작성` (한글) — **0건** (단 `google_docs_write` "Google Docs 작성"은 기존 텍스트를 Docs에 쓰는 노드, LLM 무관)

→ **도메인 특화 LLM 노드는 카탈로그에 없음**. 모든 LLM 작업은 `anthropic_chat` 1개로 커버.

### 5.3 그럼 "문서 작성"은 어떻게 일어나는가

**시나리오 예시**: 사용자 "이 PDF 요약해서 슬랙으로 보내줘"

```
1. 사용자 메시지 → Composer (신정혜) 의도 분석
2. Composer가 워크플로우 자동 생성:
   ┌──────────────────┐    ┌──────────────────┐    ┌────────────────────┐
   │ google_drive_    │───▶│ anthropic_chat   │───▶│ slack_post_message │
   │ read             │    │                  │    │                    │
   │ (PDF 텍스트      │    │ messages=[{      │    │ (요약 결과를       │
   │  추출)           │    │   "role":        │    │  Slack 채널에      │
   │                  │    │   "user",        │    │  발송)             │
   │                  │    │   "content":     │    │                    │
   │                  │    │   "다음 문서를   │    │                    │
   │                  │    │    3줄 요약해줘: │    │                    │
   │                  │    │    {input.text}" │    │                    │
   │                  │    │ }]               │    │                    │
   └──────────────────┘    └──────────────────┘    └────────────────────┘
3. 사용자 실행 → execution_engine이 각 노드 dispatch
4. anthropic_chat 노드 → process() → ❌ NotImplementedError (4번 섹션)
```

→ **"요약"이라는 의미는 anthropic_chat 노드 자체가 아니라 `messages` prompt + 이전 노드 출력 데이터 조합으로 만들어짐**.

### 5.4 책임 영역 분리 — 누가 어떤 부분을 책임지는가

| 누가                                         | 무엇을                                                                                                                                       | 영역                          |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **anthropic_chat 노드**                | LLM API 호출 wrapper 메타데이터만 (model/messages/temperature 등 입출력 schema)                                                              | 박아름 REQ-003 nodes_graph    |
| **Composer (`composer_graph.py`)**     | 사용자 메시지 의도 분석 → "이 작업엔 anthropic_chat을 써야겠다" 판단 → prompt 구성 → 워크플로우 청사진 생성 (`drafter_service`)        | 신정혜 REQ-004 ai_agent       |
| **워크플로우 작성자 (사용자)**         | Frontend UI에서 직접 anthropic_chat 노드 배치 + parameter UI에서 model/prompt 입력                                                           | REQ-010 frontend (조장)       |
| **Skills Builder (3 use case)**        | LLM 사용 의도의 SkillNode 청사진 정의 (예: `customer_support_voc_intake` "고객 VOC 분석/분류"). 워크플로우 안에서 anthropic_chat 활용 가정 | 박아름 REQ-004 skills_builder |
| **toolset connector + execution_engine** | 실제 Anthropic API HTTP 호출 + API key 주입 + 응답 처리                                                                                      | 햄햄 REQ-005 + 조장 REQ-007   |

### 5.5 Skills Builder가 만든 SkillNode 중 LLM 사용 의도의 것들

박아름 영역 5/13 등록한 30 SkillNode 중 LLM 사용이 자연스러운 SkillNode 예시:

- `customer_support_voc_intake` — "고객 VOC 접수/분류" (LLM 자연어 분류)
- `customer_support_chatbot_route` — "챗봇 라우팅" (LLM 의도 분류)
- `customer_support_csat_survey` — "CSAT 설문 분석" (LLM 텍스트 분석)
- `customer_support_kb_search` — "지식베이스 검색" (LLM RAG)
- `marketing_*` 일부 — 카피 생성, 타겟팅 분석

→ 이런 SkillNode들이 실제로 동작하려면 **워크플로우 안에 anthropic_chat 노드가 함께 배치**되어야 함. SkillNode 자체는 anthropic_chat을 직접 사용하지 않고, 워크플로우 청사진에서 활용하는 구조 가정.

### 5.6 종합 평가 — anthropic_chat 노드 역할

| 질문                              | 답변                                                            |
| --------------------------------- | --------------------------------------------------------------- |
| anthropic_chat = 문서 작성 노드?  | ❌**아니다** — Anthropic Claude API 범용 wrapper           |
| 카탈로그에 요약/보고서 전용 노드? | ❌**없다** — 모두 anthropic_chat + prompt로 처리           |
| "요약" "보고서" 의미는 어디서?    | **prompt (`messages` 필드)** — Composer가 사용자 의도 분석 후 자동 생성 |
| 사용자가 직접 만들 수 있는가?     | ✅ Frontend UI에서 anthropic_chat 노드 배치 + prompt 입력 (REQ-010 미완성) |
| Skills Builder LLM SkillNode는?   | 워크플로우 청사진 안에서 anthropic_chat을 활용하는 구조 가정    |
| 실제 LLM 호출은 작동하는가?       | ❌**아니다** — 4번 섹션 참조 (process() NotImplementedError) |

### 5.7 박아름이 조장에게 보고할 핵심 사실

> **anthropic_chat은 "문서 작성 노드"가 아니라 "Anthropic Claude API 범용 wrapper"**입니다.
>
> - input: `model` + `messages`(prompt) + 옵션
> - output: `content` + `stop_reason` + `usage`
> - "요약/보고서/이메일 생성" 같은 도메인 의미는 **prompt에 담겨 동적으로 결정**됨
>
> **"요약하기"라는 의도를 수행하는 주체는 다음 중 하나**:
>
> 1. **Composer** (신정혜) — 사용자 메시지 분석 → anthropic_chat 노드 + 적절한 prompt 자동 생성
> 2. **워크플로우 작성자** (사용자) — UI에서 직접 anthropic_chat 배치 + prompt 작성
> 3. **Skills Builder가 정의한 SkillNode** (박아름) — LLM 사용 의도의 SkillNode들이 워크플로우 청사진에서 anthropic_chat을 활용
>
> **결론**: 카탈로그에 "요약 전용", "보고서 전용" 같은 도메인 특화 LLM 노드는 없음. 모든 LLM 작업은 anthropic_chat 1개로 커버되며, 의미는 prompt에서 결정됨. 다만 현재 `process()`가 NotImplementedError라 워크플로우 실행 시 LLM 호출 자체가 작동하지 않음 (4번 섹션 참조).

---

## 6. LLM 노드 풀세트 결정 — gemma_chat 1개 신설 + anthropic_chat 보존 (5/14 야간 박아름 결정 반전)

> ## 🔄 결정 반전 알림 (5/14 야간 — 본 섹션 §6.2~§6.8 내용보다 우선)
>
> 본 섹션은 원래 "Tier 1 4개 신설 + anthropic_chat 완전 제거" (옵션 B+)로 작성됐으나, 5/14 야간 박아름이 시스템 본질 재점검 후 **gemma_chat 1개 + anthropic_chat 보존**으로 결정 반전. 의사결정 흐름 보존을 위해 원 내용(§6.2~§6.8)은 그대로 두고 본 박스를 상위 결정으로 둠.
>
> ### 최종 결정 (5/14 야간)
> - **gemma_chat 1개만 신설** (`modules/nodes_graph/adapters/catalog/external/gemma_chat.py`)
> - **anthropic_chat 보존** (development 머지된 상태 그대로, 제거 안 함)
> - **Tier 1 4개 결정 폐기** (§6.2.2 표 + §6.3 4개 spec 무효)
>
> ### 반전 근거 — 박아름 시스템 본질 정합
> - 박아름 시스템 = Composer (REQ-004 AI 에이전트)가 사용자 자연어 → 워크플로우 자동 생성 + **prompt 동적 생성**
> - 노드 책임 = "받은 prompt로 LLM 추론 1회" — 요약/분류/추출 판단은 **Composer 책임**
> - n8n 패턴(정적 prompt 박힌 용도별 노드)은 박아름 시스템에 매핑 안 됨 (n8n은 사람이 노드 선택 / 박아름은 AI 자동)
> - REQ-004 `LLMPort` 추상화도 1개 (도메인 특화 port 0건), Skills Builder `generate_structured(prompt, schema)` generic 패턴
> - anthropic_chat 1개 패턴과 카탈로그 일관성 (외부 LLM 1 + 시스템 LLM 1)
>
> ### gemma_chat 노드 사양 (PR #68 commit `8c68c7c` 적용)
> | 필드 | 값 |
> |---|---|
> | `node_type` | `gemma_chat` |
> | `name` | "Gemma Chat" |
> | `category` | `ai` |
> | `risk_level` | `LOW` |
> | `required_connections` | `[]` (시스템 LLM, 자격증명 불필요) |
> | `service_type` | `"gemma"` |
> | `is_mvp` | `True` |
> | 입력 | `prompt` (필수, Composer 동적 생성) + `response_format`("text"\|"json"\|"markdown") + `max_tokens` + `temperature` + `system` (선택) |
> | 출력 | `content` + `finish_reason` + `usage` |
> | `process()` | `NotImplementedError` → REQ-004 `ModalLLMAdapter` 위임 |
>
> ### 카탈로그 변화 (반전 후)
> - 추가: `gemma_chat` (1건)
> - 제거: 0건 (anthropic_chat 보존)
> - 최종 카탈로그: 55 + 1 = **56 노드**
>
> ### 작업 완료 상태 (5/14 야간)
> - ✅ `gemma_chat.py` 작성 (메인 브랜치 `feature/req-003-nodes-graph` 직접 commit `8c68c7c`)
> - ✅ `test_gemma_chat.py` 8 contract 테스트 (`tests/unit/adapters/`)
> - ✅ `.gitignore` SA JSON 패턴 7줄 보강 (메인 브랜치 5/9 stale에 development 동기)
> - ✅ PR #68 생성 (base=development, head=feature/req-003-nodes-graph): https://github.com/billionaireahreum/Workflow_Automation/pull/68
> - ⏸️ DB 카탈로그 갱신 (bootstrap 재실행) — PR #68 머지 후
> - ⏸️ REQ-003 spec line 490 갱신 — 별도 docs PR (박아름 5/11 anthropic_chat 시점 spec 미갱신 패턴 정합)
>
> ### Tier 1 4개 결정 폐기 이유 (의사결정 흐름 보존)
> - n8n 패턴 분석가 답변(4개 또는 5개 권장)이 정당하긴 하나 — **n8n은 사람이 노드 선택하는 UX**라 용도별 분리가 도움
> - **박아름 시스템은 AI 자동 라우팅** — Composer가 prompt 동적 생성하므로 노드 분리 효과 약함
> - 4개로 가면 `anthropic_chat` 1개와 카탈로그 비일관 (LLM별 노드 개수 정책 충돌)
> - 박아름 시스템 본질 = "prompt가 모든 의도를 담는다, 노드는 LLM 추론 실행기"
>
> ### 5/14 야간 부수 진행
> - 옵션 X (sub-branch `feature/req-003-gemma-nodes` 생성 + cherry-pick 8개) 잠시 진행 후 rollback → 박아름 5/12 룰(REQ별 메인 브랜치 누적) 재확인
> - sub-branch 안전 삭제 (commits 0)
> - 메인 브랜치 5/9 stale (`3ed7c51`)에 직접 commit → PR #68
>
> ---

### 6.1 배경 — Gemma 4 정책과 anthropic_chat의 모순 (원래 분석, 5/14 오후)

5번 섹션 후 박아름 본인이 짚은 추가 모순:
- Sprint 3 plan + REQ-004 spec: **LLM = Gemma 4 (Modal llm-base, 신정혜 영역)**
- 그런데 카탈로그에 외부 Anthropic API를 호출하는 `anthropic_chat` 노드 활성 상태
- → 박아름이 5/11에 commit `4d03e49`로 직접 만든 노드 (REQ-003 spec line 490에 명시)

**조사 결과 — 의도된 분리였음**:
- Gemma 4 (Modal llm-base) = 시스템 내부 LLM (sub-agent들이 자체 추론, 회사 비용)
- Anthropic Claude API = 사용자 워크플로우 LLM (사용자 자기 API key, 사용자 비용)

**박아름 5/14 결정**: **분리 정책 폐기 → Gemma 4 단일 백엔드로 통일**
- 이유: 외부 API 의존성 제거 + 시스템 LLM 비용 부담 없음 + Sprint 3 Gemma 4 정책 일관성

### 6.2 박아름 5/14 결정 — anthropic_chat 완전 제거 + Tier 1 4개 신설 (옵션 B+)

#### 6.2.1 anthropic_chat 완전 제거

- 파일 삭제: `modules/nodes_graph/adapters/catalog/external/anthropic_chat.py`
- REQ-003 spec line 490 갱신 (anthropic_chat 제거)
- `database/seeds/node_definitions.json` 갱신
- DB 카탈로그에서 삭제 (bootstrap 재실행 시 `--cleanup-placeholder`로 자동 제거 — 박아름 카탈로그 set에서 빠지면 삭제됨)

#### 6.2.2 신규 Gemma 4 기반 Tier 1 4개 노드 신설

업무 자동화에서 LLM이 가장 많이 쓰이는 6 카테고리 중 **카테고리 1(분석/이해)과 2(생성)에 집중된 Tier 1 4개**:

| # | node_type | 한글명 | 카테고리 | 박아름 SkillNode 매핑 |
|---|-----------|--------|---------|---------------------|
| 1 | `gemma_summarize` | Gemma 요약 | 텍스트 생성 | document_data 요약 시나리오 |
| 2 | `gemma_classify` | Gemma 분류 | 텍스트 분석 | customer_support_voc_intake, chatbot_route 등 ⭐ |
| 3 | `gemma_extract` | Gemma 정보 추출 | 텍스트 분석 | document_data 추출 시나리오 |
| 4 | `gemma_document_generate` | Gemma 문서 생성 | 텍스트 생성 | marketing_*, hr_* 문서 생성 |

#### 6.2.3 선택 이유 (옵션 B+ 채택 근거)

- **박아름 SkillNode 30종 실제 매핑** — 분류 7~10건, 추출/요약 5~7건, 생성 5~7건이 Tier 1 4개로 모두 커버
- **Composer 라우팅 명확** — 사용자 의도("이거 분류해줘") → 노드 직접 매칭 (prompt 변환 불필요)
- **BGE-M3 검색 마켓플레이스 효과** — "분류" 검색 → `gemma_classify` top-1 정확 매칭
- **prompt 템플릿 내장** — 사용자/Composer가 prompt 직접 작성 부담 0, 품질 일관성
- **시스템 LLM (비용 부담 0)** — `required_connections=[]` 자격증명 불필요
- **Sprint 3 범위 통제** — Tier 2/3 (sentiment / translate / answer / rewrite / score)은 Sprint 4 이연

### 6.3 신규 노드 spec 제안 (박아름 영역 메타데이터 작업)

#### 6.3.1 `gemma_summarize` — Gemma 요약

```python
node_type:    "gemma_summarize"
name:         "Gemma 요약"
category:     "ai"
risk_level:   LOW
is_mvp:       True
required_connections: []        # 시스템 LLM, 자격증명 불필요
service_type: "gemma"           # 또는 null
description:  "Gemma 4 LLM으로 텍스트를 요약합니다. 회의록·이메일·문서를 짧게 압축."

input_schema:
  - text: str                   # 요약할 원문
  - max_length: int = 200       # 요약 글자 수 (목표)
  - style: "bullet" | "paragraph" = "paragraph"

output_schema:
  - summary: str                # 요약 결과
  - source_length: int          # 원문 길이 (참고)
```

#### 6.3.2 `gemma_classify` — Gemma 분류 ⭐

```python
node_type:    "gemma_classify"
name:         "Gemma 분류"
category:     "ai"
risk_level:   LOW
is_mvp:       True
required_connections: []
service_type: "gemma"
description:  "Gemma 4 LLM으로 텍스트를 미리 정의된 카테고리 중 하나로 분류합니다."

input_schema:
  - text: str                   # 분류할 텍스트
  - categories: list[str]       # 분류 카테고리 목록 (예: ["환불", "배송", "기타"])
  - allow_multi: bool = False   # 복수 분류 허용 여부

output_schema:
  - category: str               # 분류 결과 (allow_multi=False일 때)
  - categories: list[str]       # 복수 분류 결과 (allow_multi=True일 때)
  - confidence: float           # 신뢰도 0~1
```

#### 6.3.3 `gemma_extract` — Gemma 정보 추출

```python
node_type:    "gemma_extract"
name:         "Gemma 정보 추출"
category:     "ai"
risk_level:   LOW
is_mvp:       True
required_connections: []
service_type: "gemma"
description:  "Gemma 4 LLM으로 자유 텍스트에서 구조화된 필드를 추출합니다 (인보이스/명함/폼)."

input_schema:
  - text: str                   # 원문 텍스트
  - schema: dict[str, Any]      # 추출할 필드 JSON Schema (예: {name, date, amount})

output_schema:
  - data: dict[str, Any]        # 추출된 구조화 데이터
  - missing_fields: list[str]   # 추출 실패한 필드 목록
```

#### 6.3.4 `gemma_document_generate` — Gemma 문서 생성

```python
node_type:    "gemma_document_generate"
name:         "Gemma 문서 생성"
category:     "ai"
risk_level:   LOW
is_mvp:       True
required_connections: []
service_type: "gemma"
description:  "Gemma 4 LLM으로 보고서/이메일/공지/메모 등 정형 문서를 생성합니다."

input_schema:
  - template_type: "report" | "email" | "announcement" | "memo"
  - data: dict[str, Any]        # 입력 데이터 (자유 dict)
  - tone: "formal" | "casual" = "formal"

output_schema:
  - document: str               # 생성된 문서
  - template_type: str          # 사용한 템플릿 (참고)
```

### 6.4 작업 범위 분리 — 박아름 영역 vs 외부 영역

| 단계 | 작업 | 영역 |
|---|---|---|
| 1 | `anthropic_chat.py` 완전 삭제 | ✅ 박아름 (REQ-003) |
| 2 | `gemma_summarize.py` 신규 (NodeDefinition + Pydantic dataclass + prompt 템플릿 메모) | ✅ 박아름 |
| 3 | `gemma_classify.py` 신규 | ✅ 박아름 |
| 4 | `gemma_extract.py` 신규 | ✅ 박아름 |
| 5 | `gemma_document_generate.py` 신규 | ✅ 박아름 |
| 6 | `modules/nodes_graph/adapters/catalog/registry.py` import 갱신 | ✅ 박아름 |
| 7 | REQ-003 spec line 490 (카탈로그 표) 갱신 — anthropic_chat 제거 + gemma 4개 추가 | ✅ 박아름 |
| 8 | `database/seeds/node_definitions.json` 갱신 | ✅ 박아름 |
| 9 | 단위 테스트 작성 (메타데이터 검증) | ✅ 박아름 |
| 10 | DB 카탈로그 갱신 (`bootstrap_node_definitions.py --cleanup-placeholder --all` 재실행) | ⏳ DB 권한 받은 후 |
| **11** | **`process()` 실제 LLM 호출 wiring (Gemma 4 호출, prompt 템플릿 + ai_agent.LLMPort 호출)** | ❌ **toolset (햄햄 REQ-005) + execution_engine (조장 REQ-007) 영역** |
| 12 | `toolset` connector에 Gemma 4 호출 경로 추가 | ❌ 햄햄 |
| 13 | `ToolsetExecutor.execute_tool` 실제 구현 | ❌ 조장 |

### 6.5 카탈로그 변화 — 카탈로그 55 → 58

- 제거: `anthropic_chat` (1건)
- 추가: `gemma_summarize` + `gemma_classify` + `gemma_extract` + `gemma_document_generate` (4건)
- 순증: +3건

**최종 카탈로그**: 55 + 3 = **58 노드** (도메인 28 + 외부 13(anthropic_chat 제외) + Gemma 4 + toolset 14 + 신규 Gemma 4)

> 정확한 분류: 도메인 28(트리거6 + 흐름8 + 데이터14) + 외부 12(anthropic_chat 제외, http_request/slack/gmail/...) + AI 4 (gemma_*) + toolset 14 = **58**

### 6.6 의존성 방향 위반 회피 패턴

CLAUDE.md "modules 간 허용된 교차 import" 표:
- `ai_agent → nodes_graph` ✅
- **`nodes_graph → ai_agent` ❌ 허용 목록 없음**

→ 박아름 `gemma_*.py`의 `process()` 메서드도 anthropic_chat과 동일 패턴 — `NotImplementedError` raise. 실제 LLM 호출은 toolset/execution_engine 영역에서 ai_agent의 `LLMPort` 사용.

```python
async def process(self, input: GemmaSummarizeInput) -> GemmaSummarizeOutput:
    raise NotImplementedError(
        "Gemma 4 LLM 호출은 REQ-005 toolset connector를 통해 처리. "
        "ai_agent.LLMPort (ModalLLMAdapter)를 toolset/execution_engine이 주입."
    )
```

### 6.7 향후 확장 — Tier 2/3 Sprint 4 이연

Sprint 4 검토 가능 (현재 결정 아님):

| Tier | 노드 | 카테고리 |
|------|------|----------|
| **Tier 2** | `gemma_sentiment` | 감성 분석 |
| **Tier 2** | `gemma_translate` | 번역 |
| **Tier 2** | `gemma_answer` | 답변 생성 / RAG |
| **Tier 2** | `gemma_compare` | 비교 평가 |
| **Tier 3** | `gemma_rewrite` | 재작성 |
| **Tier 3** | `gemma_score` | 점수화 |

→ Sprint 3 = **Tier 1 4개로 통제**. 향후 사용 패턴 보면서 Tier 2 추가 검토.

### 6.8 박아름 다음 액션 (코드 작업)

다음 commit 묶음 예상:
1. `modules/nodes_graph/adapters/catalog/external/anthropic_chat.py` 삭제
2. `modules/nodes_graph/adapters/catalog/external/gemma_summarize.py` 신규
3. `modules/nodes_graph/adapters/catalog/external/gemma_classify.py` 신규
4. `modules/nodes_graph/adapters/catalog/external/gemma_extract.py` 신규
5. `modules/nodes_graph/adapters/catalog/external/gemma_document_generate.py` 신규
6. `modules/nodes_graph/adapters/catalog/registry.py` import 갱신
7. `docs/specs/REQ-003-nodes-graph.md` line 490 갱신
8. `database/seeds/node_definitions.json` 갱신
9. `modules/nodes_graph/tests/unit/adapters/test_*.py` 신규/갱신
10. `modules/ai_agent/report/sprint-3-week1-2026-05-14-skills-builder.md` 추가 진행 반영

commit 메시지 예상:
```
feat(nodes-graph): anthropic_chat 제거 + Gemma 4 기반 Tier 1 4개 노드 신설

Sprint 3 LLM 정책(Gemma 4 단일 백엔드) 일관성 + 박아름 SkillNode 30종
실제 매핑 기반 Tier 1 4개 (summarize/classify/extract/document_generate).
박아름 5/14 옵션 B+ 결정.

- anthropic_chat 완전 제거 (외부 API 의존성 제거)
- gemma_summarize / gemma_classify / gemma_extract / gemma_document_generate 신규
- REQ-003 spec line 490 갱신 (AI 카테고리 1 → 4)
- database/seeds/node_definitions.json 갱신
- 단위 테스트 신규/갱신

실제 LLM 호출은 process() NotImplementedError 유지 (anthropic_chat 동일 패턴).
toolset connector + execution_engine wiring은 햄햄·조장 영역 후속.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## 종합 결론 — 조장 보고용 한 줄 요약

| 영역                                     | 상태                                            | 핵심                                                                                                                                                          |
| ---------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Auth**                        | ⚠️**백엔드 100% / e2e flow 70%**        | 박아름 영역 완성, REQ-009 api_server + REQ-010 frontend 후속 필요                                                                                             |
| **2. Node**                        | ✅**자세히 고려됨**                       | document/adapter/운영 3단계 + 결정론적 uuid5 + 5/13 BGE-M3 검색 77.8% 검증                                                                                    |
| **3. Skill Builder**               | ✅**책임 경계 확정 (옵션 A, 5/14 박아름 결정)** | Skills Builder = 스킬 생성 전용 (입력 → 추출 → DB upsert → 끝). 워크플로우 생성은 Composer 영역. 옵션 B(확장)는 Sprint 4 이연. **추가 작업 0건** |
| **4. 카탈로그 AI 노드 (LLM 호출)** | ⚠️**메타데이터만 / 실행 wiring 차단**   | `anthropic_chat` 1건 활성, `process()` NotImplementedError. REQ-005 toolset + REQ-007 execution_engine 미완성. anthropic/openai/Gemma 4 어디에도 연결 0건 |
| **5. anthropic_chat 역할**         | ✅**명확 — 범용 LLM wrapper**            | "문서 작성 전용" 노드 아님. 요약/보고서/이메일 등 의미는 prompt에서 결정. Composer가 사용자 의도 분석해서 anthropic_chat + prompt로 워크플로우 자동 생성        |
| **6. LLM 노드 풀세트 (Gemma 4)**   | ✅**5/14 야간 결정 반전 — gemma_chat 1개 신설 + anthropic_chat 보존 (PR #68)** | 시스템 본질 정합 (Composer가 prompt 동적 생성 → 노드는 LLM 추론 실행기 1개로 충분). anthropic_chat 1개 패턴과 카탈로그 일관성. Tier 1 4개 결정 폐기. PR #68: https://github.com/billionaireahreum/Workflow_Automation/pull/68 |

### 박아름이 조장에게 요청할 결정 사항

**~~(A) Skill Builder 책임 경계 (3번 영역)~~** — ✅ 5/14 박아름 본인 결정으로 옵션 A 채택, 추가 협의 불필요. 메모리 박힘.

**~~(B) 카탈로그 AI 노드 실행 wiring (4번 영역)~~** — ✅ 5/14 박아름 본인 결정으로 옵션 2(Gemma 4 단일 백엔드) 채택. 5/14 야간 반전 결정: **gemma_chat 1개 신설 + anthropic_chat 보존** (6번 섹션 상단 반전 박스 참조, PR #68). 메모리 박힘.

**(C) gemma_chat 1개 실행 wiring (6번 영역, 향후 작업)**:

- 박아름 메타데이터 정의 완료 (PR #68 commit `8c68c7c`) — `process()`는 NotImplementedError 패턴 유지 (의존성 방향 위반 회피, anthropic_chat 동일 패턴)
- **toolset connector (햄햄 REQ-005)**: Gemma 4 호출 경로 추가 (ai_agent.LLMPort 활용)
- **execution_engine (조장 REQ-007)**: `ToolsetExecutor.execute_tool` 실제 구현
- → 박아름 영역 메타데이터 commit 후 햄햄·조장에게 wiring 요청

---

## 7. 박아름 액션 아이템 (압축판, 우선순위순)

### ✅ 완료 (5/14 후반)
1. **DB 권한 검증 e2e** — 조장 GRANT 처리 후 재실행 → `upserted_count=4, failed_count=1` (customer_support 1건 cold start fail)
2. **timeout 30→180s 선반영** (commit `157c261`, 신정혜 PR #56 `9d50311b` 동기화)
3. **timeout 180s 적용 e2e 재실행** (it_ops 5종) → `upserted_count=5, failed_count=0` ✅ **Test plan #3 완전 통과**

### 🟡 단기 (이번 commit 묶음 — Tier 1 4개 신설)
3. `modules/nodes_graph/adapters/catalog/external/anthropic_chat.py` **완전 제거**
4. `gemma_summarize.py` 신규 (요약)
5. `gemma_classify.py` 신규 (분류) ⭐
6. `gemma_extract.py` 신규 (정보 추출)
7. `gemma_document_generate.py` 신규 (문서 생성)
8. `modules/nodes_graph/adapters/catalog/registry.py` import 갱신
9. REQ-003 spec line 490 갱신 (AI 카테고리 1 → 4)
10. `database/seeds/node_definitions.json` 갱신
11. 단위 테스트 신규/갱신
12. bootstrap 재실행 (`--cleanup-placeholder --all` → 카탈로그 58 row)
13. commit + push (PR #51 추가 commit)

### 🟢 PR #56 머지 후
- bootstrap_node_definitions.py 임시 timeout 180s 교체 코드 제거

### 🔵 PR #51 머지 후 별도 docs PR
- CLAUDE.md line 172 + REQ-004 spec line 95/437 stale 정정 (embedder_port nodes_graph SSOT)
- (선택) REQ-004 §2.2에 Skills Builder 책임 경계 "옵션 A 확정" 명시

### ⏸️ 박아름 영역 외부 (대기 / 위임)
- **toolset connector** (햄햄 REQ-005): Gemma 4 호출 경로 추가 — Tier 1 4개 실제 LLM 호출 wiring
- **execution_engine** (조장 REQ-007): `ToolsetExecutor.execute_tool` 실제 구현
- PR #56 머지 (신정혜 또는 조장 권한)
- 신정혜 SSOT 갱신 PR 머지 (health path + SSE dual 명시)
- 햄햄 PR #54 머지 (agent_memory 마이그레이션 트리거)

---

## 참조

- spec: `docs/specs/REQ-004-ai-agent.md` §2.2, §2.4
- 가이드: `docs/guides/sub_agent_modal_deploy.md` §1.3
- 메모리: `feedback_branch_strategy.md`, `feedback_db_safety.md`
- 5/13 보고서: `modules/ai_agent/report/sprint-3-week1-2026-05-13-skills-builder.md`
- 5/14 보고서: `modules/ai_agent/report/sprint-3-week1-2026-05-14-skills-builder.md`
- PR #51: https://github.com/billionaireahreum/Workflow_Automation/pull/51
- PR #56: https://github.com/billionaireahreum/Workflow_Automation/pull/56
- PR #54: https://github.com/billionaireahreum/Workflow_Automation/pull/54
