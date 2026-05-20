# ADR-0018: 워크플로우 노드 독립 실행 경로 — ToolsetExecutor 폐기, BaseNode.process() 직접 실행

- **Status**: Accepted
- **Date**: 2026-05-20 (초안 — 조장 방향 제시 + 영향평가), 2026-05-20 (PR #105 머지 — 합의 확정)
- **Deciders**: @dhwang0803-glitch (조장), @billionaireahreum (박아름), @gawon714-gif (햄햄) — 박아름·햄햄 방향 승인 (PR #105)
- **Tags**: area/execution_engine, area/nodes_graph, area/toolset, area/auth, layer/adapter, catalog

## Context

ADR-0014는 두 가지를 동시에 결정했다.

- **§45-51 (Tool≠Node SSOT)**: Tool = AI Agent 내부 호출(`BaseTool`), Node = 사용자 캔버스(`BaseNode`).
- **§40-43 (호출 경로 #6)**: 경로 A = `workflow node → execution_engine.ToolsetExecutor → toolset.execute_tool()`.

경로 A는 §45-51 원칙과 모순된다 — 사용자 캔버스 노드의 실행이 agent 전용 도구 계층(toolset)에 의존한다. 이 모순은 ADR-0014 작성 시점(toolset 모듈이 막 채워진 5/19)에는 "11종 `BaseTool` 재사용으로 비용 절감"이라는 실리로 수용됐다.

2026-05-20 Phase F 풀스택 smoke 후속 점검에서 다음이 확인됐다.

- `services/execution_engine/src/dependencies/container.py`가 `ToolsetExecutor`를 **단일** node_executor로 wiring + `_noop` 더미 → 워크플로우 노드 실행 0건.
- `nodes_graph/adapters/catalog/external/` 25종 `process()`는 전부 `NotImplementedError`("ToolsetExecutor 위임" 메시지). `domain/catalog/` 28종은 `process()` 실구현 완료.
- 즉 노드 실행 계층은 사실상 미구축 상태이며, 경로 A는 코드로 완성된 적이 없다.

조장 결정: **toolset은 agent 전용으로 한정하고, 워크플로우 노드는 toolset에 의존하지 않는 독립 실행 경로를 갖는다.**

## Decision

1. **ADR-0014 §6 경로 A 폐기.** 워크플로우 노드 실행 = `BaseNode.process()` 직접 호출. (§45-51 Tool≠Node 원칙은 유지·강화.)

2. **execution_engine — 단일 `CatalogNodeExecutor`.** `ToolsetExecutor` / `LangGraphDispatcher` / `SandboxExecutor`(현재 미사용) 제거. 신규 `CatalogNodeExecutor`가 `node_type → BaseNode 인스턴스 조회 → await process(input, context)`를 53종 노드에 동일하게 수행. sync Celery worker ↔ async `process()` 브리지 포함.

3. **`BaseNode.process()` 시그니처 확장** — `process(self, input)` → `process(self, input, context: NodeContext)`. `NodeContext`는 해결된 connection 토큰 + 실행 메타(execution_id, user_id)를 담는다. 53종 전체 적용(domain 28종은 context 무시). `NodeContext`는 nodes_graph·execution_engine 공유 타입이므로 `common_schemas`에 정의.

4. **external 25종 `process()` 실구현** — "connections > app" 구조로 구현. domain 28종은 기구현이라 (2)만으로 즉시 실행 가능.
   - **toolset 중복 11종** (rest_api·graphql·webhook·file_read·file_write·file_transform·email_send·slack_notify·data_mapping·json_transform·text_template) — toolset `BaseTool` 로직을 node `process()`로 **포팅**. 포팅 시 toolset `SecureConnectorPort`(`connector`)는 **nodes_graph 측 구현에서 사용하지 않고** httpx 직접 호출(`RestApiTool`의 connector-less 경로가 이미 그 형태). toolset의 `SecureConnectorPort` Port·어댑터 자체는 그대로 유지 — agent 경로용, **toolset 모듈 무변경**. credential은 `kwargs["credential"].value` → `context.connection_token` 1:1 치환 — 이식 비용은 "dict→dataclass 변환" 수준.
     - transform 3 + file 3: connection 미사용 → 순수 로직 이식(`context` 무시).
     - api 3 + notification 2: `context` connection 토큰 사용.
   - **비-toolset 14종** (anthropic_chat·gemma_chat·http_request·bigquery/mysql/postgresql_query·gmail_send·google_* 4·linear_create_issue·pdf_generate·slack_post_message) — 참고 구현 없음, connections+app 구조로 그린필드 신규 구현.

5. **connection 주입 = `auth.CredentialInjectionService` 재사용.** node 위험도(RESTRICTED) 게이트 + `required_connections` 검증 + 복호화를 한 묶음으로 수행. `CatalogNodeExecutor`가 `inject(node.credential_id, node.node_id)` 호출 → `NodeContext`에 적재 → `process()` 종료 후 `PlaintextCredential.wipe()`.

6. **credential resolver 통합** — `credentials` 테이블(DDL 002, 통합 vault)을 해결 SSOT로 둔다. `CredentialInjectionService`는 현재 `oauth_connections`만 조회 → OAuth 앱만 지원. API-key 방식 앱(Anthropic, DB query 등)도 해결하도록 `credentials.credential_kind` 기반 분기를 추가한다. OAuth 앱은 `oauth_connections` 메타로 enrich.
   - **Port 소유 경계**: resolver는 `auth`가 **이미 소유한** `CredentialRepository` Port(`auth/domain/ports/credential_repository.py`, `get_by_id`)에 의존 — 신규 Port 불필요(`AuthenticateUseCase`가 이미 사용 중). 경계는 기존 Clean Architecture 그대로: Port 계약 = auth, 구현 = storage(`pg_credential_repository`, PR #99), `credentials` 테이블 DDL = database(DDL 002).

7. **toolset 11종 `BaseTool` 유지** — agent 호출 경로(ADR-0014 경로 B)용. toolset 모듈은 본 ADR로 변경 없음.

8. **단계화 (sprint 일정 제약)** — ① `CatalogNodeExecutor` + domain 28종 실행(executor만으로 동작) → ② external `is_mvp` 노드 우선 구현 → ③ 나머지 external. sprint 3(~5/31) 내 external 25종 풀구현은 비현실적.

## Consequences

### 긍정

- Tool≠Node 원칙이 코드 레벨에서 일관 — 노드 실행이 toolset과 완전 분리.
- execution_engine 단순화 — node executor 3개 → 1개. toolset/credential 이중 경로 딜레마 소멸.
- `CatalogNodeExecutor` 도입 즉시 domain 28종 실행 가능(`process()` 기구현).
- credential resolver 통합으로 OAuth 앱 + API-key 앱 단일 처리.

### 부정 / 제약

- `BaseNode.process()` 시그니처 변경 — `BaseNode` + 53종 + 테스트 영향(domain 28종은 기계적).
- external 25종 `process()` 실구현 ~1,500~3,500 LOC(개략) — 본 변경의 최대 비용. ADR-0014가 노렸던 "11종 toolset 재사용" 절감을 포기.
- ADR-0014 §3 "`process()` NotImplementedError + ToolsetExecutor 위임" 패턴 폐기 → external 25종 스텁 메시지 + `nodes_graph/README.md` L80 + `catalog_registry.py` L55 + `plan/sprint-3-catalog-plugin-discovery.md` 문서 정합 필요.
- `OAuthConnection.service`가 `Literal["google", "slack"]` — 신규 provider(github/linear/anthropic 등) 추가 시 확장 필요.
- file 3종(file_read/write/transform)은 toolset 구현이 로컬 FS(`pathlib`) 기반 — Cloud Run worker 임시 컨테이너에선 의미가 약함. 포팅과 별개로 file 노드의 스토리지 타깃(GCS 등) 결정이 후속으로 필요.

### 외부 모듈 영향

- **execution_engine** (REQ-007, 황대원) — `CatalogNodeExecutor` 신규 + container 재배선 + `_noop` 제거. ~150~300 LOC.
- **nodes_graph** (REQ-003, 박아름) — `BaseNode` 시그니처 + external 25종 `process()` 실구현 + 문서 정합. **최대 비용.**
- **auth** (REQ-002, 박아름) — `CredentialInjectionService` resolver 통합(Decision 6) + `OAuthConnection.service` 확장.
- **common_schemas** (REQ-012, 황대원) — `NodeContext` 신규 공유 타입.
- **toolset** (REQ-005, 햄햄) — 변경 없음(agent 경로 유지).
- **DB** — `node_definitions` node_type 불변. 영향 거의 없음.

## Alternatives Considered

### (A) ADR-0014 경로 A 유지

- ❌ Tool≠Node 원칙과의 모순 지속. 노드 실행이 agent 도구 계층에 영구 결합.

### (B) execution_engine이 toolset `BaseTool`을 직접 호출 (경량안)

- 11종 toolset 로직 재사용 → 비용 최소.
- ❌ "toolset = agent 전용" 원칙 위반. execution_engine ↔ toolset 결합 잔존.

### (C) 11종을 toolset `BaseTool`에서 nodes_graph `process()`로 포팅 (완전 분리 — 본 ADR 채택)

- 현재 toolset 중복 11종의 동작 로직은 **toolset `BaseTool`에만 존재**하고, nodes_graph `external/` 측 `process()`는 `NotImplementedError` 스텁이다("toolset.X을 통해 처리, `process()` 직접 호출 X" 메시지).
- 본 ADR은 toolset `BaseTool` 로직을 nodes_graph `process()`로 포팅한다(Decision 4). nodes_graph 측 구현은 `SecureConnectorPort`를 사용하지 않고 httpx 직접 호출 — toolset 도구가 이미 connector-less 경로를 갖고 있어 이식이 기계적이다. toolset의 `SecureConnectorPort` Port는 유지(toolset 무변경).
- 결과적으로 동작 로직이 toolset(agent용)과 nodes_graph(canvas용) 양쪽에 의도적으로 존재하게 되며, 양측은 이후 독립 진화한다. toolset 측 11종은 변경하지 않는다(agent 경로 유지).

## Related ADRs

- **ADR-0014** — §6 경로 A를 본 ADR이 개정. 본 ADR이 Accepted 되면 ADR-0014 §6에 `Superseded in part by ADR-0018` marker를 추가한다.
- ADR-0013 — Port SSOT 패턴.
- ADR-0008 — `NodeExecutionState` 공유 타입(common_schemas 배치 선례).

## References

- 영향평가 세션: 2026-05-20 (Phase F 후속 점검)
- 조사 근거: `nodes_graph/adapters/catalog/external/*` 25종 `process()` 스텁, `domain/catalog/*` 28종 실구현, `execution_engine/src/dependencies/container.py:155`, `auth/domain/services/credential_injection_service.py`, DDL `002_credentials_agents_webhooks.sql` / `008_oauth_security.sql`
