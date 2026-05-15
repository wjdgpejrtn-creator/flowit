# 조장 검증 요청 결과 — Auth / Node / Skill Builder 3 영역

**검증 일자**: 2026-05-15 (금) — 5/14 초안 작성 후 5/15 §1.5/§6/§8/§9 갱신 + docs PR 반영
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

#### 1.5 의존성 발견 (5/15 검증 추가)

- `modules/auth/domain/services/credential_injection_service.py:6` — `from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository` import 존재
- CLAUDE.md "modules 간 허용된 교차 import" 표에 `auth → nodes_graph/domain/ports` 라인 **누락**
- 의존성 자체는 합리적 (auth가 노드 정의의 `required_connections` / `risk_level` 검증에 사용), 코드 변경 불필요
- → **CLAUDE.md 표에 1줄 추가 필요** (조장 협의 → §9.1 협의 사항 참조)

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
>
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

| 필드                           | 값                            | 위치                                                                                                                            |
| ------------------------------ | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **node_type**            | `anthropic_chat`            | `modules/nodes_graph/adapters/catalog/external/anthropic_chat.py:57-103` (`get_node_definition()` 내부 NodeDefinition 인자) |
| **name**                 | "Anthropic Chat"              | 같은 파일                                                                                                                       |
| **category**             | `"ai"`                      | 같은 파일                                                                                                                       |
| **is_mvp**               | `True` ✅ **활성**    | 비활성 보류 5종(Outlook/Teams/OneDrive/OpenAI Chat/Notion)에 포함되지 않음                                                      |
| **required_connections** | `["anthropic"]`             | 외부 Anthropic API 자격증명 필요                                                                                                |
| **service_type**         | `"anthropic"`               | —                                                                                                                              |
| **risk_level**           | `MEDIUM`                    | —                                                                                                                              |
| NodeDefinition 정의 위치       | `anthropic_chat.py:100-103` | —                                                                                                                              |

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

| 누가                                           | 무엇을                                                                                                                                      | 영역                          |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **anthropic_chat 노드**                  | LLM API 호출 wrapper 메타데이터만 (model/messages/temperature 등 입출력 schema)                                                             | 박아름 REQ-003 nodes_graph    |
| **Composer (`composer_graph.py`)**     | 사용자 메시지 의도 분석 → "이 작업엔 anthropic_chat을 써야겠다" 판단 → prompt 구성 → 워크플로우 청사진 생성 (`drafter_service`)        | 신정혜 REQ-004 ai_agent       |
| **워크플로우 작성자 (사용자)**           | Frontend UI에서 직접 anthropic_chat 노드 배치 + parameter UI에서 model/prompt 입력                                                          | REQ-010 frontend (조장)       |
| **Skills Builder (3 use case)**          | LLM 사용 의도의 SkillNode 청사진 정의 (예:`customer_support_voc_intake` "고객 VOC 분석/분류"). 워크플로우 안에서 anthropic_chat 활용 가정 | 박아름 REQ-004 skills_builder |
| **toolset connector + execution_engine** | 실제 Anthropic API HTTP 호출 + API key 주입 + 응답 처리                                                                                     | 햄햄 REQ-005 + 조장 REQ-007   |

### 5.5 Skills Builder가 만든 SkillNode 중 LLM 사용 의도의 것들

박아름 영역 5/13 등록한 30 SkillNode 중 LLM 사용이 자연스러운 SkillNode 예시:

- `customer_support_voc_intake` — "고객 VOC 접수/분류" (LLM 자연어 분류)
- `customer_support_chatbot_route` — "챗봇 라우팅" (LLM 의도 분류)
- `customer_support_csat_survey` — "CSAT 설문 분석" (LLM 텍스트 분석)
- `customer_support_kb_search` — "지식베이스 검색" (LLM RAG)
- `marketing_*` 일부 — 카피 생성, 타겟팅 분석

→ 이런 SkillNode들이 실제로 동작하려면 **워크플로우 안에 anthropic_chat 노드가 함께 배치**되어야 함. SkillNode 자체는 anthropic_chat을 직접 사용하지 않고, 워크플로우 청사진에서 활용하는 구조 가정.

### 5.6 종합 평가 — anthropic_chat 노드 역할

| 질문                              | 답변                                                                             |
| --------------------------------- | -------------------------------------------------------------------------------- |
| anthropic_chat = 문서 작성 노드?  | ❌**아니다** — Anthropic Claude API 범용 wrapper                          |
| 카탈로그에 요약/보고서 전용 노드? | ❌**없다** — 모두 anthropic_chat + prompt로 처리                          |
| "요약" "보고서" 의미는 어디서?    | **prompt (`messages` 필드)** — Composer가 사용자 의도 분석 후 자동 생성 |
| 사용자가 직접 만들 수 있는가?     | ✅ Frontend UI에서 anthropic_chat 노드 배치 + prompt 입력 (REQ-010 미완성)       |
| Skills Builder LLM SkillNode는?   | 워크플로우 청사진 안에서 anthropic_chat을 활용하는 구조 가정                     |
| 실제 LLM 호출은 작동하는가?       | ❌**아니다** — 4번 섹션 참조 (process() NotImplementedError)              |

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

## 6. LLM 노드 풀세트 결정 — gemma_chat 1개 신설 + anthropic_chat 보존 (5/14 야간 박아름 결정)

본 섹션은 박아름 카탈로그의 AI 카테고리 노드 풀세트에 대한 5/14 결정 과정과 최종 결과를 정리합니다. 5/14 오후에는 옵션 B+(Tier 1 4개 신설 + anthropic_chat 제거)를 검토했으나, 야간 시스템 본질 재점검 결과 gemma_chat 1개 + anthropic_chat 보존으로 결정 반전했습니다.

### 6.1 최종 결정 (5/14 야간)

- **gemma_chat 1개만 신설** (`modules/nodes_graph/adapters/catalog/external/gemma_chat.py`)
- **anthropic_chat 보존** (development 머지된 상태 그대로, 제거 안 함)
- **Tier 1 4개 결정 폐기** (5/14 오후 옵션 B+ 분석은 §6.7 부록 참조)

### 6.2 반전 근거 — 박아름 시스템 본질 정합

- 박아름 시스템 = Composer (REQ-004 AI 에이전트)가 사용자 자연어 → 워크플로우 자동 생성 + **prompt 동적 생성**
- 노드 책임 = "받은 prompt로 LLM 추론 1회" — 요약/분류/추출 판단은 **Composer 책임**
- n8n 패턴(정적 prompt 박힌 용도별 노드)은 박아름 시스템에 매핑 안 됨 (n8n은 사람이 노드 선택 / 박아름은 AI 자동)
- REQ-004 `LLMPort` 추상화도 1개 (도메인 특화 port 0건), Skills Builder `generate_structured(prompt, schema)` generic 패턴
- anthropic_chat 1개 패턴과 카탈로그 일관성 (외부 LLM 1 + 시스템 LLM 1)

### 6.3 gemma_chat 노드 사양 (PR #68 commit `8c68c7c` 적용)

| 필드                     | 값                                                                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `node_type`            | `gemma_chat`                                                                                                                           |
| `name`                 | "Gemma Chat"                                                                                                                             |
| `category`             | `ai`                                                                                                                                   |
| `risk_level`           | `LOW`                                                                                                                                  |
| `required_connections` | `[]` (시스템 LLM, 자격증명 불필요)                                                                                                     |
| `service_type`         | `"gemma"`                                                                                                                              |
| `is_mvp`               | `True`                                                                                                                                 |
| 입력                     | `prompt` (필수, Composer 동적 생성) + `response_format` ("text"\|"json"\|"markdown") + `max_tokens` + `temperature` + `system` |
| 출력                     | `content` + `finish_reason` + `usage`                                                                                              |
| `process()`            | `NotImplementedError` → REQ-004 `ModalLLMAdapter` 위임 (의존성 방향 위반 회피, anthropic_chat 동일 패턴)                            |

### 6.4 카탈로그 변화 (반전 후)

- 추가: `gemma_chat` (1건)
- 제거: 0건 (anthropic_chat 보존)
- 최종 카탈로그: 55 + 1 = **56 노드**

**분류 (56 노드 기준)**:

- 도메인 28종 (트리거 6 + 흐름 8 + 데이터 14)
- 외부 14종 (anthropic_chat + gemma_chat 포함, http_request / slack / gmail / google_docs 등)
- toolset 14종 (REQ-005 영역)

### 6.5 의존성 방향 위반 회피 패턴

CLAUDE.md "modules 간 허용된 교차 import" 표:

- `ai_agent → nodes_graph` ✅
- **`nodes_graph → ai_agent` ❌ 허용 목록 없음**

→ 박아름 `gemma_chat.py`의 `process()` 메서드도 anthropic_chat과 동일 패턴 — `NotImplementedError` raise. 실제 LLM 호출은 toolset/execution_engine 영역에서 ai_agent의 `LLMPort` 사용.

```python
async def process(self, input: GemmaChatInput) -> GemmaChatOutput:
    raise NotImplementedError(
        "Gemma 4 LLM 호출은 REQ-005 toolset connector를 통해 처리. "
        "ai_agent.LLMPort (ModalLLMAdapter)를 toolset/execution_engine이 주입."
    )
```

### 6.6 작업 완료 상태 (5/14 야간 박아름 영역 모두 완료)

| # | 작업                                                                                               | 위치 / commit                                                    |
| - | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 1 | `gemma_chat.py` 작성 (90줄, NodeDefinition + Pydantic dataclass)                                 | `feature/req-003-nodes-graph` commit `8c68c7c`               |
| 2 | `test_gemma_chat.py` 8 contract 테스트                                                           | `modules/nodes_graph/tests/unit/adapters/test_gemma_chat.py`   |
| 3 | `catalog_registry.py` 갱신 (명시 import + return 추가)                                           | commit `fbc9365`                                               |
| 4 | `.gitignore` SA JSON 패턴 7줄 보강                                                               | commit `8c68c7c`                                               |
| 5 | `database/seeds/node_definitions.json` 갱신 (총 56 노드)                                         | commit `0112444`                                               |
| 6 | REQ-003 spec line 490 갱신 (AI 카테고리 1 → 2)                                                    | commit `0112444`                                               |
| 7 | DB 카탈로그 갱신 (bootstrap `--cleanup-placeholder --all` 재실행, 85 → 86 row, embedding 86/86) | 5/14 야간 실행 완료                                              |
| 8 | PR #68 생성                                                                                        | https://github.com/billionaireahreum/Workflow_Automation/pull/68 |

#### 실행 wiring 잔여 (박아름 영역 외부)

| 단계 | 작업                                              | 담당                           |
| ---- | ------------------------------------------------- | ------------------------------ |
| 1    | `process()` 실제 LLM 호출 wiring (Gemma 4 호출) | ❌ 햄햄 REQ-005 + 조장 REQ-007 |
| 2    | `toolset` connector에 Gemma 4 호출 경로 추가    | ❌ 햄햄                        |
| 3    | `ToolsetExecutor.execute_tool` 실제 구현        | ❌ 조장                        |

→ 박아름 영역 메타데이터 완료, 실행 wiring은 햄햄·조장에게 인계.

### 6.7 의사결정 흐름 부록 — 5/14 오후 옵션 B+ 분석 (폐기됨)

> **의사결정 흐름 보존 목적**. 5/14 오후에는 anthropic_chat 완전 제거 + Tier 1 4개 신설(`gemma_summarize` / `gemma_classify` / `gemma_extract` / `gemma_document_generate`)을 검토했습니다. 그러나 야간에 박아름이 시스템 본질을 재점검한 결과 옵션 B+ 폐기, gemma_chat 1개로 통일했습니다.

**옵션 B+ 검토 내용 (요약, 폐기됨)**:

- LLM 6 카테고리 중 카테고리 1(분석/이해) + 2(생성)에 집중된 Tier 1 4개:
  - `gemma_summarize` (요약), `gemma_classify` (분류), `gemma_extract` (정보 추출), `gemma_document_generate` (문서 생성)
- 박아름 SkillNode 30종 매핑: 분류 7~10건, 추출/요약 5~7건, 생성 5~7건 커버
- BGE-M3 검색 효과 (예: "분류" → `gemma_classify` top-1)
- prompt 템플릿 내장으로 사용자 부담 0
- Sprint 3 범위 통제 (Tier 2/3 Sprint 4 이연)

**옵션 B+ 폐기 이유 (5/14 야간 재점검)**:

- n8n 패턴 분석가 답변(용도별 4~5개 권장)은 **사람이 노드 선택하는 UX**에 적합
- 박아름 시스템은 **AI 자동 라우팅** — Composer가 prompt 동적 생성하므로 노드 분리 효과 약함
- 4개로 가면 `anthropic_chat` 1개와 카탈로그 비일관 (LLM별 노드 개수 정책 충돌)
- 박아름 시스템 본질 = "prompt가 모든 의도를 담는다, 노드는 LLM 추론 실행기"

**5/14 야간 부수 진행 (참고)**:

- 옵션 X (sub-branch `feature/req-003-gemma-nodes` 생성 + cherry-pick) 잠시 진행 후 rollback → 박아름 5/12 룰(REQ별 메인 브랜치 누적) 재확인
- sub-branch 안전 삭제 (commits 0), 메인 브랜치 직접 commit → PR #68

> Tier 2/3 확장(`gemma_sentiment` / `translate` / `answer` / `compare` / `rewrite` / `score`)은 Sprint 4 이연. 사용 패턴 보고 재검토.

---

## 종합 결론 — 조장 보고용 한 줄 요약

| 영역                                     | 상태                                                                                  | 핵심                                                                                                                                                                                                                           |
| ---------------------------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **1. Auth**                        | ⚠️**백엔드 100% / e2e flow 70%**                                              | 박아름 영역 완성, REQ-009 api_server + REQ-010 frontend 후속 필요                                                                                                                                                              |
| **2. Node**                        | ✅**자세히 고려됨**                                                             | document/adapter/운영 3단계 + 결정론적 uuid5 + 5/13 BGE-M3 검색 77.8% 검증                                                                                                                                                     |
| **3. Skill Builder**               | ✅**책임 경계 확정 (옵션 A, 5/14 박아름 결정)**                                 | Skills Builder = 스킬 생성 전용 (입력 → 추출 → DB upsert → 끝). 워크플로우 생성은 Composer 영역. 옵션 B(확장)는 Sprint 4 이연.**추가 작업 0건**                                                                       |
| **4. 카탈로그 AI 노드 (LLM 호출)** | ⚠️**메타데이터만 / 실행 wiring 차단**                                         | `anthropic_chat` 1건 활성, `process()` NotImplementedError. REQ-005 toolset + REQ-007 execution_engine 미완성. anthropic/openai/Gemma 4 어디에도 연결 0건                                                                  |
| **5. anthropic_chat 역할**         | ✅**명확 — 범용 LLM wrapper**                                                  | "문서 작성 전용" 노드 아님. 요약/보고서/이메일 등 의미는 prompt에서 결정. Composer가 사용자 의도 분석해서 anthropic_chat + prompt로 워크플로우 자동 생성                                                                       |
| **6. LLM 노드 풀세트 (Gemma 4)**   | ✅**5/14 야간 결정 반전 + 5/15 PR #68 머지 완료** — gemma_chat 1개 신설 + anthropic_chat 보존, development에 4 commits 흡수 (commit `f2e21c5`) | 시스템 본질 정합 (Composer가 prompt 동적 생성 → 노드는 LLM 추론 실행기 1개로 충분). anthropic_chat 1개 패턴과 카탈로그 일관성. Tier 1 4개 결정 폐기. PR #68 머지 완료: https://github.com/billionaireahreum/Workflow_Automation/pull/68 |

### 박아름이 조장에게 요청할 결정 사항

**~~(A) Skill Builder 책임 경계 (3번 영역)~~** — ✅ 5/14 박아름 본인 결정으로 옵션 A 채택, 추가 협의 불필요. 메모리 박힘.

**~~(B) 카탈로그 AI 노드 실행 wiring (4번 영역)~~** — ✅ 5/14 박아름 본인 결정으로 옵션 2(Gemma 4 단일 백엔드) 채택. 5/14 야간 반전 결정: **gemma_chat 1개 신설 + anthropic_chat 보존** (6번 섹션 상단 반전 박스 참조, PR #68). 메모리 박힘.

**(C) gemma_chat 1개 실행 wiring (6번 영역, 향후 작업)**:

- 박아름 메타데이터 정의 완료 (PR #68 commit `8c68c7c`) — `process()`는 NotImplementedError 패턴 유지 (의존성 방향 위반 회피, anthropic_chat 동일 패턴)
- **toolset connector (햄햄 REQ-005)**: Gemma 4 호출 경로 추가 (ai_agent.LLMPort 활용)
- **execution_engine (조장 REQ-007)**: `ToolsetExecutor.execute_tool` 실제 구현
- → 박아름 영역 메타데이터 commit 후 햄햄·조장에게 wiring 요청

---

## 7. 박아름 액션 아이템 (압축판, 우선순위순) — 5/14 야간 결정 반전 반영

> ⚠️ **결정 반전 (5/14 야간)**: §6 상단 박스 참조. Tier 1 4개 신설 결정 폐기 → gemma_chat 1개 신설 + anthropic_chat 보존. 본 §7도 그에 맞춰 갱신.

### ✅ 완료 (5/14 후반 + 야간)

1. **DB 권한 검증 e2e** — 조장 GRANT 처리 후 재실행 → `upserted_count=4, failed_count=1` (customer_support 1건 cold start fail)
2. **timeout 30→180s 선반영** (commit `157c261`, 신정혜 PR #56 `9d50311b` 동기화)
3. **timeout 180s 적용 e2e 재실행** (it_ops 5종) → `upserted_count=5, failed_count=0` ✅ **Test plan #3 완전 통과**
4. **결정 #2 반전** — Tier 1 4개 → gemma_chat 1개 (시스템 본질 정합: Composer가 prompt 동적 생성)
5. **anthropic_chat 보존** — development에 그대로 (제거 안 함, 옵션 1)
6. **gemma_chat.py 신설** — `modules/nodes_graph/adapters/catalog/external/gemma_chat.py` (PR #68 commit `8c68c7c`, 90 lines)
7. **단위 테스트 신설** — `modules/nodes_graph/tests/unit/adapters/test_gemma_chat.py` (8 contract 테스트)
8. **`.gitignore` SA JSON 패턴 7줄 보강** — 메인 브랜치 5/9 stale → development 동기 (PR #68 포함)
9. **REQ-003 spec 갱신** — AI 카테고리 1 → 2 (anthropic_chat + gemma_chat), 합계 55 → 56 (commit `0112444`)
10. **`database/seeds/node_definitions.json` 갱신** — gemma_chat row 추가 (총 56 노드, commit `0112444`)
11. **PR #68 생성** — base=development, head=feature/req-003-nodes-graph: https://github.com/billionaireahreum/Workflow_Automation/pull/68
12. **PR #68 충돌 해결** — development merge (commit `9459852`) → mergeable=MERGEABLE/CLEAN 복귀
13. **5/14 보고서 §9 + verification §6 결정 반전 박스 + 메모리 갱신** — 의사결정 흐름 영구 보존

### ✅ 단기 (5/14 야간 모두 완료)

- ✅ **bootstrap 실 실행** (PR #68 머지 전 박아름 단독 진행, --cleanup-placeholder --all 2회 실행). 1차 미등록 발견 → registry 갱신 후 2차 정합. 결과: BEFORE=85 → AFTER=86, embedding 86/86 (gemma_chat BGE-M3 포함)
- ✅ **`modules/nodes_graph/application/catalog_registry.py` 갱신** (PR #68 commit `fbc9365`) — Plugin discovery는 디렉터리 자동 스캔 아님, **명시적 import + return 패턴** 확인 (박아름 5/12 카탈로그 패턴 정합)
- ⏳ **bootstrap_node_definitions.py 임시 timeout 180s 코드 제거** — 정혜 PR #56 `9d50311b` 본질 해결 + development merge로 메인 브랜치 흡수 완료 (commit `9459852`). 다만 bootstrap 내부 임시 패치 라인 cleanup 선택 (동작 무관)

### 🔍 5/14 야간 인증 진단 (박아름 직관 정확)

- 시도 1 (실패): `GOOGLE_APPLICATION_CREDENTIALS_JSON` 환경 변수 (Modal Secret 전용 패턴) → `InvalidAuthorizationSpecificationError` 반복
- 박아름 짚음: "이전 5/12/13 실행한 코드처럼 해" → bootstrap 스크립트 분석 결과 표준 GCP ADC 패턴 (`GOOGLE_APPLICATION_CREDENTIALS=<file path>`) 확인
- 박아름 5/13 보고서 line 188 명시: Modal app boot()이 JSON content → 임시 파일 + 표준 ADC 변수 등록. 로컬은 변환 단계 없이 직접 파일 경로
- 시도 2 (성공): `$env:GOOGLE_APPLICATION_CREDENTIALS = "<SA JSON 파일 경로>"` → 인증 통과 → bootstrap 정상 실행

### 🔵 docs PR — ✅ PR #69 생성 완료 (2026-05-15)

> PR #51은 5/14 머지 완료(`15d0f87`). 5/15 약속분 모두 묶어서 **PR #69 (docs PR) 생성 완료** — 조장 리뷰 대기 중.
> **PR URL**: https://github.com/billionaireahreum/Workflow_Automation/pull/69

**PR #69 반영 사항**:

| 파일                                   | 정정 내용 |
| -------------------------------------- | -------- |
| `CLAUDE.md`                          | 카탈로그 종 수 54 → 56 / 교차 import 표 `auth → nodes_graph` + `toolset → nodes_graph` 추가 / `EmbeddingPort` → `EmbedderPort` 예외 패턴 명시 (line 5, 138, 141, 178) |
| `docs/specs/REQ-004-ai-agent.md`     | `EmbeddingPort` → `EmbedderPort` (line 95, 148, 149) |
| `MONOREPO_STRUCTURE.md`              | `EmbeddingPort` → `EmbedderPort` (line 99, 408) |
| `docs/context/clean_architecture.md` | `EmbeddingPort` → `EmbedderPort` (line 363, 1274, 1510) |
| 본 verification 보고서                | §1.5 신규 + §4.1 라인 정정 + §6 재작성 (Y옵션) + §8 FAQ 신규 + §9 협의 사항 신규 |

**제외 항목 (PR #69 scope 외)**:
- `docs/context/clean_architecture.md` line 903 `SkillEmbedderPort` — REQ-008 marketplace 영역, 조장 별도 확인
- REQ-004 spec §2.2 Skills Builder "옵션 A 확정" 명시 — 선택 사항 (필요 시 별도 docs PR)

→ **commit**: `f5419a2` / **변경**: 5 파일 / +386 / -293

### ⏸️ 박아름 영역 외부 (대기 / 위임)

- **toolset connector** (햄햄 REQ-005): Gemma 4 호출 경로 추가 — **gemma_chat 1개 wiring** (Tier 1 4개 → 1개로 갱신)
- **execution_engine** (조장 REQ-007): `ToolsetExecutor.execute_tool` 실제 구현
- PR #68 머지 (조장 권한)
- 햄햄 PR #54 머지 (agent_memory 마이그레이션 트리거)
- 신정혜 SSOT 갱신 PR 머지 (health path + SSE dual 명시 — commit `3a8715c7` 일부 반영)

---

## 8. FAQ — 추가 검증 9건 (2026-05-15 박아름 정리, SSOT 비교 포함)

5/14 사용자가 짚은 추가 9건 질문에 대해 박아름 영역(auth / node graph / skill builder)과 기타로 분리해서 정리. 각 답변은 SSOT(spec + 코드 + CLAUDE.md)와 비교 검증.

### 8.1 auth 영역

→ **블록 1 9건에 auth 관련 질문 없음**. 미인증 시 로그인 유도 흐름은 §1.3 기존 답변 참조.

### 8.2 node graph 영역 (박아름 REQ-003)

#### Q. 노드가 뭘로 구성됐는가

- **DB 총 86 row** (5/14 야간 bootstrap 결과):
  - 카탈로그 노드 56종 (`catalog_registry.py` 명시 등록, PR #68 gemma_chat 포함)
  - SkillNode 30종 (Skills Builder가 추출, is_mvp=False)
- 카테고리 구성 (REQ-003 spec §"카탈로그"):
  - communication: Slack / Gmail / Outlook / Teams 등
  - storage: Google Drive / OneDrive 등
  - data: CSV / JSON / Excel
  - http: REST API / webhook
  - ai: anthropic_chat (외부) + gemma_chat (내부 Gemma 4) 2종

**SSOT 비교**:

- `database/seeds/node_definitions.json` 카탈로그 56 row ↔ `catalog_registry.py` 56종 일치
- REQ-003 spec line 490 카탈로그 카테고리 명시와 코드 정합

#### Q. GraphValidator는 뭐?

- **위치**: `modules/nodes_graph/domain/services/graph_validator.py:18` (박아름 영역)
- **역할**: 워크플로우 그래프 무결성 검증 서비스
- **검증 5가지**:
  1. 중복 instance_id
  2. 사이클 감지 (Kahn's algorithm)
  3. 노드 타입 불일치 (`from_handle` ↔ `to_handle`)
  4. 고립 노드 검출
  5. 필수 연결 누락 (`required_connections`)
- **사용처**: Workflow Composer (신정혜) `validator_node`에서 호출. CLAUDE.md "주요 실행 흐름"에 "최대 3회 retry" 명시

**SSOT 비교**:

- REQ-003 spec GraphValidator 정의 ↔ `graph_validator.py:32` `validate()` 시그니처 일치
- REQ-004 spec §3.2 13-노드 그래프 `validator_node` ↔ Composer가 GraphValidator 호출 정합

### 8.3 skill builder 영역 (박아름 Sprint 3)

#### Q. "스킬 만들어줘" 명령은 누가 설계? LLM 입력 → Skills Builder 동작?

- **트리거 영역**: **Main Orchestrator (신정혜 영역)** — `modules/ai_agent/application/agents/orchestrator/route_request_use_case.py:9`
- **흐름**: 사용자 메시지 → IntentAnalyzerService(LLM) → `intent=build_skill` 분기 → `skills_node`(HTTP) → agent-skills-builder Modal app
- **박아름 영역**: 트리거 후 입력(SOP 문서 / industry_code / domain_code) 받아서 use case 3개 중 하나 실행 → SkillNode 추출 → DB upsert

**SSOT 비교**:

- `route_request_use_case.py:9` 분기 명시: `intent=build_skill → skills_node` ↔ REQ-004 spec §3.1 supervisor diagram 일치
- 박아름 use case는 spec §2.2 line 127-131 그대로 구현 (옵션 A)

#### Q. "슬랙으로 메시지 보내고 싶어" vs "이 워크플로우로 스킬 만들어줘"

| 사용자 발화                     | intent 분류                  | 라우팅         | 결과                       |
| ------------------------------- | ---------------------------- | -------------- | -------------------------- |
| "슬랙으로 메시지 보내고 싶어"   | `draft` (또는 `clarify`) | composer       | WorkflowSchema 생성        |
| "이 워크플로우로 스킬 만들어줘" | `build_skill`              | skills_builder | SkillNode 추출 + DB upsert |

- **분기 결정자**: Orchestrator `IntentAnalyzerService` (신정혜 영역)
- **박아름 작업 영역**: build_skill 분기 도착 후만

**SSOT 비교**:

- `route_request_use_case.py:7-10` docstring 분기 명시 ↔ 코드 일치
- REQ-004 spec §3.1 5가지 intent (`draft/refine/clarify/build_skill/propose`)

#### Q. 직무별 baseline 25종 — 신규 입사 채팅 — 누가 짜는지

> **✅ 조장 답변 받음 (2026-05-15)**: "25종" 발언은 박아름 baseline `functional_domain`/`industry_default`와 **신규 직원 온보딩 가이드 문서 업로드 → 스킬 생성 use case**가 혼동된 표현. 박아름 baseline과는 무관. **박아름 영역은 11종 유지**.

- **현재 구현 (5/15 시점)**:
  - **functional_domain (직무) 5종** — 박아름: customer_support / document_data / hr / it_ops / marketing
  - **industry_default (산업) 6종** — 박아름: ecommerce / food / it / manufacturing / service / wholesale_retail
  - 합계 **11종** (조장 답변 후 확정 — 25종 추가 작업 불필요)
- **신규 직원 온보딩 use case (조장 답변 기반)**: 온보딩 가이드 문서를 업로드하면 `BuildFromSOPUseCase`가 LLM으로 SkillNode 추출 → DB upsert (박아름 영역 이미 구현 완료, PR #45 머지)
- **채팅으로 영역 선택 분기**: Orchestrator/Composer (신정혜) — IntentAnalyzerService 또는 SlotFillQuestionFrame multi-turn
- **baseline JSON 추가 작업자**: 박아름 (필요 시 seed JSON만 추가하면 자동 적용)

**SSOT 비교**:

- REQ-004 spec line 139 `modules/ai_agent/seeds/functional_domain_defaults/{code}.json` ↔ 박아름 5종 일치
- spec §2.2 `BuildFromFunctionalDomainUseCase` 시그니처 ↔ 구현 일치
- spec §2.2 `BuildFromSOPUseCase` 시그니처 ↔ 온보딩 문서 use case 구현 일치 (조장 답변 정합)

### 8.4 기타 (박아름 영역 외부)

#### Q. LangGraph 안 쓰는 이유 + 대신 뭐?

- **전제 정정**: 박아름 시스템은 **LangGraph 쓰고 있음** (신정혜 영역에서)
- **사용처 (신정혜)**:
  - `modules/ai_agent/adapters/langgraph/composer_graph.py` — Workflow Composer 13-노드 StateGraph
  - `modules/ai_agent/adapters/langgraph/supervisor_graph.py` — Main Orchestrator supervisor
- **박아름 영역 (skills_builder)**: LangGraph **사용 안 함** — use case 3개 단순 입력/추출/upsert 패턴으로 충분 (그래프 분기 불필요)

**SSOT 비교**:

- REQ-004 spec line 116 "LangGraph supervisor 패턴" / line 165 `LangGraphOrchestrator` / line 202 "13-노드 StateGraph" ↔ 신정혜 코드 일치
- CLAUDE.md "기술 스택" `AI 에이전트 = LangGraph` 명시 ↔ 정합

#### Q. 박아름 담당 4 Frame (AgentNodeFrame / SlotFillQuestionFrame / ResultFrame / ErrorFrame)

- **정정 필요**: 4 Frame은 **박아름 담당 아님** — **REQ-012 common_schemas (조장 영역)** 정의. 박아름은 사용만 함
- **SSOT 위치**: `packages/common_schemas/python/common_schemas/transport.py`

| Frame                               | 필드 (SSOT)                            | 의미                       | 박아름 사용                                   |
| ----------------------------------- | -------------------------------------- | -------------------------- | --------------------------------------------- |
| `AgentNodeFrame` (line 21)        | `agent_node_name: str`               | 어느 단계 진행 중인지      | ✅ skills_builder route 핸들러                |
| `SlotFillQuestionFrame` (line 31) | `question: str`, `field_name: str` | LLM이 사용자에게 추가 질문 | ❌ Composer 영역 (clarify branch)             |
| `ResultFrame` (line 42)           | `intent: str`, `payload: dict`     | 최종 결과                  | ✅ upserted_count 등 반환                     |
| `ErrorFrame` (line 48)            | `code: str`, `message: str`        | 에러 통보                  | ✅ error 종결 시 (+ complete frame 추가 5/14) |

- **추가 Frame (SSOT에 더 있음)**: `SessionFrame`, `RationaleDeltaFrame`, `DraftSpecDeltaFrame` — Composer 영역 전용

**SSOT 비교**:

- `transport.py` 정의 ↔ 사용자 메모 4건 모두 일치 (필드명 + 의미)
- 단 박아름이 SlotFillQuestionFrame 사용 0건 (clarify branch는 Composer 영역)

#### Q. Modal이 뭐?

- **정의**: GPU 서버리스 컴퓨팅 플랫폼 (CLAUDE.md "기술 스택" — `Modal GPU (Gemma 4 + BGE-M3)`)
- **박아름 시스템에서의 역할**:
  - LLM 호스팅: Gemma 4 (텍스트 생성) + BGE-M3 (임베딩 768d)
  - sub-agent 4종 배포: `llm-base` / `orchestrator` / `agent-composer` / `agent-skills-builder`
- **박아름 영역**: `services/agents/agent-skills-builder/main.py` Modal app (5/14 deploy 완료)

**SSOT 비교**:

- `docs/guides/sub_agent_modal_deploy.md` — Modal 배포 가이드 (조장 영역)
- CLAUDE.md "기술 스택" LLM = Modal GPU 명시
- REQ-004 spec §3.1 — sub-agent별 Modal app 배포 명시

#### Q. Workflow Composer = 1회성 (new workflow 버튼) — UI 구조 (왼쪽 채팅 / 오른쪽 노드)

- **영역**: REQ-010 frontend (조장 영역) — 박아름 영역 외부
- **트리거 흐름 (조장 발언 기반)**:
  - "new workflow" 버튼 → 새 워크플로우 페이지
  - 왼쪽 채팅창 → 사용자 메시지 → Orchestrator → Composer 라우팅
  - 오른쪽 노드 그래프 → Composer가 생성한 WorkflowSchema 실시간 렌더링 (React Flow)
- **박아름 작업 영역**: 0건 — frontend + Composer + Orchestrator 모두 외부

**SSOT 비교**:

- CLAUDE.md "프론트엔드 = Next.js 14 + React Flow + Zustand" 명시
- REQ-010 spec — 5/15 시점 미확인 (조장 영역, 박아름 review 우선순위 아님)

#### Q. 의도 장기적 vs 단기적 → 각 에이전트 라우팅

> **✅ 조장 답변 받음 (2026-05-15)**: "장기적/단기적"은 의도 분류(intent)가 아니라 **메모리 저장 정책 논의**. 두 영역:
> 1. **Main Agent 채팅 내역**: 단기(in-memory) vs 장기(파일 기반) 저장 결정
> 2. **Personalization 사용자 패턴**: 단기(in-memory) vs 장기(파일 기반) 저장 결정
>
> → Orchestrator(신정혜) + Personalization(햄햄) 영역. **Skill Builder(박아름) 무관**. 박아름 작업 0건.

- **의도 분류 SSOT (실제 코드)**: `draft / refine / clarify / build_skill / propose` (5가지, route_request_use_case.py:7-10) — 5/15 변경 없음
- **장기/단기 = 메모리 저장 정책 (조장 답변)**: 박아름 영역 외부
- **라우팅 분기 구현**: Orchestrator `RouteRequestUseCase` (신정혜 영역)

**SSOT 비교**:

- `route_request_use_case.py:7-10` 5가지 intent 분기 명시 ↔ REQ-004 spec §3.1 일치
- 장기/단기 메모리 정책은 Orchestrator(신정혜) + Personalization(햄햄) 영역 — 박아름 검증 범위 외

### 8.5 종합 — 답변/적용 매트릭스

| 영역                                               | 답변 추가   | SSOT 정합                                         | 박아름 후속 액션                                               |
| -------------------------------------------------- | ----------- | ------------------------------------------------- | -------------------------------------------------------------- |
| 8.1 auth                                           | (질문 없음) | —                                                | —                                                             |
| 8.2 node graph (노드 구성 + GraphValidator)        | ✅ §8.2    | ✅ 일치                                           | 0건                                                            |
| 8.3 skill builder (트리거 흐름 + 분기 + baseline)  | ✅ §8.3    | ✅ 일치 — **조장 답변(5/15) 후 11종 확정**: 25종은 온보딩 문서 use case 혼동 표현 | **0건** (조장 답변 후 확장 작업 불필요)                       |
| 8.4 기타 (LangGraph + Frame + Modal + UI + 장단기) | ✅ §8.4    | ✅ — **조장 답변(5/15)**: 장기/단기는 메모리 저장 정책(Orchestrator + Personalization 영역), 의도 분류와 무관 | **0건** (Skill Builder 무관, 박아름 영역 외부)                |

---

## 9. 협의 사항 (조장·팀원 협의 필요)

> 본 보고서 작성 + 검증 과정에서 발견된, 박아름 단독 결정 불가능한 영역. 조장과 협의 + 각 담당자와 협의 후 처리 예정.

### 9.1 CLAUDE.md 협의 사항 (조장과)

CLAUDE.md는 프로젝트 전체 의존성 표 + 카탈로그 종 수 등 SSOT 성격이라 박아름 단독 수정 불가. 조장 협의 후 docs PR로 일괄 처리 예정.

> **✅ PR #69 (docs PR) 일괄 반영 완료 (2026-05-15)** — 5건 모두 commit `f5419a2`로 처리. 조장 리뷰 대기 중.
> PR URL: https://github.com/billionaireahreum/Workflow_Automation/pull/69

| # | 항목 | 정정 내용 | 상태 |
|---|---|---|---|
| 1 | **"modules 간 허용된 교차 import" 표** — `auth → nodes_graph` 추가 | `\| auth \| nodes_graph의 domain/ports \| from nodes_graph.domain.ports import NodeDefinitionRepository \|` 추가 (CredentialInjectionService 의존, §1.5) | ✅ PR #69 반영 |
| 2 | **"modules 간 허용된 교차 import" 표** — `toolset → nodes_graph` 추가 | `\| toolset \| nodes_graph의 application/use_cases \| from nodes_graph.application.use_cases import SearchNodesUseCase \|` 추가 (햄햄 NodeSearchPort) | ✅ PR #69 반영 |
| 3 | **"Port → Adapter 매핑" 표** — line 178 `EmbeddingPort` → `EmbedderPort` | `nodes_graph/domain/ports/EmbedderPort` + 예외 패턴 명시 (PR #30 5/12 결정) | ✅ PR #69 반영 |
| 4 | **카탈로그 종 수** line 5 — 54종 → 56종 | "56종 노드 카탈로그(외부 14 + 도메인 28 + toolset 14)" | ✅ PR #69 반영 |
| 5 | **"Port → Adapter 매핑" 표** — `EmbedderPort` 예외 패턴 보강 | line 178 정정에서 통합 처리 (#3과 동일) | ✅ PR #69 반영 |

### 9.2 각 기능별 협의 사항 (담당자별)

#### 9.2.1 신정혜 (REQ-004 ai-agent — Composer / Orchestrator)

| 항목 | 상태 |
|---|---|
| PR #56 SSE dual 종결 + health path | ✅ commit `3a8715c` SSOT 갱신 PR로 처리 완료 (5/14 development 머지) |
| PR #56 보강 권고 #1 (token leak) + #5 (keep_warm) | ⏳ 신정혜 후속 PR 대상, 박아름 영역 무관 |
| **RouteRequestUseCase 의도 분류 명칭** — "장기적/단기적" SSOT 명시 없음 | ⏳ 조장 발언 출처 확인 후 spec 갱신 필요. 현재 코드 = `draft / refine / clarify / build_skill / propose` 5가지 (§8.4 Q. 의도 분류 참조) |

#### 9.2.2 햄햄 (REQ-005 toolset)

| 항목 | 상태 |
|---|---|
| **toolset_nodes.py 14종 제거 협의** | ✅ **5/15 햄햄 11종 분류 받음 + 박아름 전면 동의 + 햄햄 재카톡 실수 박아름 정정 + 햄햄 재확인** — 003 브랜치 체크아웃 + 프로젝트 구조 전수 점검 후 박아름 답변 발송 완료 |
| **햄햄 11종 분류** — Node 유지 6 / Internal Tool 5 | ✅ Node 유지 6종 (`rest_api` / `graphql` / `webhook` / `email_send` / `slack_notify` / `text_template`) → `external/`로 이동. Internal Tool 5종 (`json_transform` / `data_mapping` / `file_read` / `file_write` / `file_transform`) → `toolset` 영역 BaseTool 신설 (햄햄 영역). 근거: "Tool = AI 내부 / Node = 사용자 workflow" 원칙 + 보안·경로 노출 우려 |
| **5/15 후반 햄햄 분류 변경 카톡 발생 + 박아름 정정 + 햄햄 재확인 (의사결정 흐름 보존)** | 5/15 후반 햄햄이 "11종 모두 external/ 일원화" 카톡 발송 — 5종(`json_transform`/`data_mapping`/`file_*`)을 Internal Tool에서 external/로 변경 시도. 박아름이 이전 분류 vs 이번 분류 비교 + file_* 보안 우려 + json/data 복잡 변환 AI 내부 처리 우려 + 작업 범위 영향(시간 5~7h 증가) 짚어서 명확화 요청. **햄햄 응답: "카톡에 실수가 있었어요, 이전 5/15 분류 그대로가 맞아요"** — 박아름 지적 정확 인정 + 이전 분류 그대로 유지 확정. 메모리에 이전 분류 미저장으로 인한 혼선이었음. → **최종 확정: Node 유지 6 + Internal Tool 5 + 제거 3, 박아름 작업 범위 external/ 6 파일 + 14종 제거 + 3~4h 그대로 유지** |
| **박아름 toolset 정리 PR 브랜치 결정** | ✅ **박아름 별도 PR 확정** (햄햄 동의 받음, 5/15) — 햄햄이 "feature/req-005-toolset 브랜치 범위"라고 제안했으나 박아름이 별도 PR로 양해 부탁 → 햄햄 응답: "nodes_graph 영역이라 REQ-003 메인 브랜치로 별도 PR 내시는 게 추적성이나 책임 분리 면에서 훨씬 깔끔한 것 같아요. 순서(PR #71 머지 → development sync → 박아름 PR)도 맞고요. 진행 OK입니다." 근거: 박아름 룰 [[feedback_branch_strategy]] REQ별 메인 브랜치 영구 보존 + nodes_graph 영역 책임 박아름 + 추적 명확성. **흐름 합의**: PR #71 머지 → development sync → REQ-003 메인 브랜치 commit → 박아름 새 PR 생성 |
| **중복 ~~3건~~ → 2건 정정** (박아름 첫 답변 정정) | ✅ `http_request_tool` → `external/http_request` 통일 / `conditional`·`loop` → `domain/catalog/control/if_condition` + `loop_list` 통일. **`slack_notify`는 별개 노드 확정** — `slack_post_message`(OAuth Bot + chat.postMessage + Block Kit) vs `slack_notify`(Incoming Webhook URL 단순 알림), 인증 방식 다름. 박아름 5/15 003 코드 정밀 비교 후 첫 답변 정정 |
| **NodeSearchPort 위치** (`toolset/adapters/node_search_adapter.py`) | ✅ 박아름 동의 (5/15 답변 발송) |
| **NodeSearchPort 의존성 방향** (`toolset → nodes_graph application/use_cases`) | ✅ **PR #69로 CLAUDE.md 갱신 완료** (위 9.1 항목 #2) |
| **한 줄 정리 보강** (햄햄 자료에 박아름 영역 비-DB Port 3건 누락) | ✅ **PR #69로 처리 완료** — EmbedderPort 예외 패턴 명시 (위 9.1 항목 #3·#5) |
| **Skills Builder SkillNode 30종 영향 평가** | ✅ **0건 확인** — `modules/ai_agent/seeds/functional_domain_defaults/*.json` 5개 + `industry_defaults/*.json` 6개 전수 grep 결과, Internal Tool 5종(`json_transform` / `data_mapping` / `file_*`) 사용 0건. Skills Builder 작업 변경 불필요 |
| **박아름 toolset 정리 PR** (별도, PR #68 + 햄햄 PR 머지 후 진행) | ⏳ 작업 내용: `toolset_nodes.py` + `tool_to_node_wrapper.py` 삭제 + `external/` 6 파일 신규 (`rest_api.py` / `graphql.py` / `webhook.py` / `email_send.py` / `slack_notify.py` / `text_template.py`) + `catalog_registry.py` 갱신 + `database/seeds/node_definitions.json` 갱신 + DB cleanup (86 → 78 row 예상) + 테스트 6 신규 + 14 제거 + REQ-003 spec line 490 갱신. 소요 3~4h |
| **카탈로그 종 수 변화** (예상, 박아름 PR 머지 후) | 현재 56 (domain 28 + external 14 + toolset 14) → 변경 후 **48** (domain 28 + external 20 + toolset 0). DB row 86 → 78 (SkillNode 30 변경 없음) |
| PR #54 머지 (agent_memory 마이그레이션 트리거) | ⏳ 햄햄 머지 시점 대기, 박아름 영역 변경 0건 |
| **NodeSearchTool 위치** (`ai_agent/adapters/tools/`) — 햄햄 5/15 정혜님 대상 메시지에서 의견 요청 | ⏳ Orchestrator/Composer LangGraph 등록 위치는 신정혜 영역, 박아름 직접 답 없음 |

#### 9.2.3 조장 (REQ-009 api-server / REQ-010 frontend / REQ-007 execution-engine)

| 항목 | 우선순위 | 상태 |
|---|---|---|
| **auth e2e flow 완성** — `/auth/callback` 라우터 추가 + Frontend OAuth redirect | 🔴 Critical | ❌ REQ-009/010 미구현 (백엔드 100% 완성, §1.4 참조) |
| **anthropic_chat / gemma_chat `process()` wiring** — `ToolsetExecutor.execute_tool` 구현 | 🟡 High | ❌ REQ-007 미완성 (§4.6 + §6.6 참조). 박아름 메타데이터 + REQ-005 toolset connector 둘 다 준비됨 |
| **PR #68 리뷰 + 머지** (gemma_chat 신설, 카탈로그 56종) | 🟡 High | ✅ **2026-05-15 03:18 박아름 셀프 머지 완료** (`f2e21c5`). development에 4 commits 흡수, gemma_chat 카탈로그 도달. 햄햄 gemma_* `process()` wiring 작업 시작 트리거 (햄햄 카톡 알림 발송 완료) |
| **PR #69 리뷰 + 머지** (docs PR — CLAUDE.md SSOT 협의 5건 + EmbedderPort stale 정정 + verification 보고서 갱신) | 🟡 High | ⏳ 2026-05-15 박아름 생성, 조장 approval 대기 |
| **baseline 25종 출처 확인** — 현재 spec/코드 = 11종 (functional 5 + industry 6), 25종은 어디서? | 🟢 Medium | ✅ **2026-05-15 조장 답변 받음** — 25종은 박아름 baseline과 **신규 직원 온보딩 문서 업로드 use case** 혼동 표현. 박아름 영역 무관, 11종 유지. 추가 작업 0건 |
| **"장기적/단기적" 의도 분류 출처 확인** — SSOT 명시 없음, 실제 코드 = 5가지 | 🟢 Medium | ✅ **2026-05-15 조장 답변 받음** — 의도 분류가 아니라 **메모리 저장 정책** (Main Agent 채팅 내역 + Personalization 사용자 패턴의 in-memory(단기) vs 파일(장기) 결정). Orchestrator/Personalization 영역, Skill Builder 무관. 박아름 작업 0건 |

#### 9.2.4 김진형 (REQ-006 doc-parser) — 박아름 협의 0건

박아름 영역과 직접 의존 없음. PR #60 (doc-parser XLSX 호환성 + 이커머스 도메인 fixture)은 박아름 영역 변경 무관.

---

## 참조

- spec: `docs/specs/REQ-004-ai-agent.md` §2.2, §2.4, §3.1, §3.2
- 가이드: `docs/guides/sub_agent_modal_deploy.md` §1.3
- 메모리: `feedback_branch_strategy.md`, `feedback_db_safety.md`, `feedback_pull_merged_prs.md`
- SSOT — common_schemas Frame: `packages/common_schemas/python/common_schemas/transport.py`
- SSOT — GraphValidator: `modules/nodes_graph/domain/services/graph_validator.py`
- SSOT — Orchestrator 라우팅: `modules/ai_agent/application/agents/orchestrator/route_request_use_case.py`
- SSOT — LangGraph 사용처: `modules/ai_agent/adapters/langgraph/composer_graph.py`, `supervisor_graph.py`
- 5/13 보고서: `modules/ai_agent/report/sprint-3-week1-2026-05-13-skills-builder.md`
- 5/14 보고서: `modules/ai_agent/report/sprint-3-week1-2026-05-14-skills-builder.md`
- PR #51: https://github.com/billionaireahreum/Workflow_Automation/pull/51
- PR #56: https://github.com/billionaireahreum/Workflow_Automation/pull/56
- PR #54: https://github.com/billionaireahreum/Workflow_Automation/pull/54
- PR #68: https://github.com/billionaireahreum/Workflow_Automation/pull/68
