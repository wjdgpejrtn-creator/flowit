# Sprint 3 Plan — 멀티 에이전트 구조 전환 + 풀스택 MVP 배포

> 기간: 2026-05-11(월) ~ 2026-05-31(일), 21일
> 목표: GCP Cloud Run 배포 완료, 외부 도메인 접근 가능, 4개 화면 동작, Modal GPU + Gemma 4 + BGE-M3 실연동의 풀스택 MVP

---

## 1. 핵심 결정사항 (Sprint 3 시작 전 합의)

| 항목 | 결정 |
|------|------|
| 완성 기준 | GCP 배포 + 외부 접근 가능 (Cloud Run 도메인) |
| Frontend 범위 | 4개 화면 모두 (Canvas + Chat + Execution + Document Viewer) |
| LLM 통합 깊이 | Modal GPU + Gemma 4 + BGE-M3 풀스택 |
| ai_agent 구조 | **멀티 에이전트로 전환** — Main Orchestrator + 3 Sub-Agent |
| Sub-Agent 배포 구조 | **에이전트별 Modal app + HTTP 통신 (옵션 2)** — 각 멤버가 본인 에이전트 자율 배포 |
| Modal app 간 인증 | **VPC 내부 통신만 허용 (옵션 C)** — 외부 차단, 인증 없음 |
| Skills Builder 입력 채널 | Frontend Document Viewer에 통합 ("이 문서로 skills 생성" 버튼) |
| 산업 표준 default | Seed 5개 산업 (제조/서비스/도소매/음식점/IT) — 박아름 작성, LLM 자유생성은 v2 |
| Personalization 저장 | GCS 파일 기반 (Claude Code memory.md 패턴 — `MEMORY.md` 인덱스 + 개별 `.md`) |

---

## 2. 멀티 에이전트 구조

### 2.1 에이전트 분장

| 에이전트 | 역할 | 담당자 | Modal app 이름 |
|---------|------|--------|---------------|
| **Main Orchestrator** | LangGraph supervisor, sub-agent 라우팅, personal memory 로드 | 신정혜 | `orchestrator` |
| **Workflow Composer** | 사용자 채팅 → 워크플로우 초안·완성 | 신정혜 | `agent-composer` |
| **Skills Builder** | SOP 문서/산업 default → skills 노드 생성 | 박아름 | `agent-skills-builder` |
| **Personalization** | 사용자 패턴 추출 → memory.md 갱신·로드 | 햄햄(이가원) | `agent-personalization` |
| **LLM Base** | Gemma 4 inference + BGE-M3 embedding | 신정혜 | `llm-base` |

### 2.2 Modal Workspace 구조

```
Modal workspace: workflow-automation (VPC 내부 통신만)
├── app: llm-base                    ← 신정혜 (5/12 1회 배포 후 안정)
├── app: orchestrator                ← 신정혜 (LangGraph supervisor)
├── app: agent-composer              ← 신정혜
├── app: agent-skills-builder        ← 박아름
└── app: agent-personalization       ← 햄햄
```

각 멤버는 본인 에이전트 코드 수정 후 `modal deploy` 자율 실행. 다른 멤버 영향 없음.

### 2.3 코드 레이아웃

```
modules/ai_agent/
├── domain/
│   ├── entities/          # AgentState, MemoryEntry, PersonalSkill, SkillNode
│   ├── ports/             # LLMPort, EmbeddingPort, AgentMemoryRepository, PersonalMemoryStore (신규)
│   └── services/          # IntentAnalyzer, DrafterService, QAEvaluator, SlotFilling (기존)
├── application/
│   └── agents/            # 신규 — sub-agent별 use case 묶음
│       ├── orchestrator/
│       │   └── route_request_use_case.py
│       ├── workflow_composer/
│       │   ├── compose_workflow_use_case.py
│       │   └── continue_conversation_use_case.py
│       ├── skills_builder/
│       │   ├── build_from_sop_use_case.py
│       │   └── build_from_industry_default_use_case.py
│       └── personalization/
│           ├── load_user_memory_use_case.py
│           ├── update_user_memory_use_case.py
│           └── recall_personal_skills_use_case.py
└── adapters/
    ├── langgraph/         # Main Orchestrator supervisor graph
    ├── llm/modal_*        # Modal Gemma 4 + BGE-M3 어댑터
    └── memory/            # PersonalMemoryStore 구현
        └── gcs_memory_store.py
```

### 2.4 Inter-Agent 통신 계약 (5/12 sync에서 확정)

`common_schemas/agent_protocol.py`에 정의 (전 sub-agent 공통):

```python
# 입력
{
  "session_id": "uuid",
  "user_id": "uuid",
  "state": AgentState,           # common_schemas
  "personal_memory": list[MemoryEntry]
}

# 출력
{
  "frames": list[SSEFrame],      # 9종 transport frame
  "state_delta": dict,
  "next_action": "continue" | "complete" | "error"
}
```

### 2.5 Personalization Agent — Claude Code memory 패턴

GCS user별 prefix에 저장:

```
gs://workflow-automation-personal/
  users/{user_id}/
    MEMORY.md              # 인덱스
    user_role.md           # type: user
    workflow_patterns.md   # type: feedback
    favorite_nodes.md      # type: project
    integrations.md        # type: reference
```

발동:
- 세션 시작: `LoadUserMemoryUseCase` → Orchestrator state에 주입
- 워크플로우 완료: `UpdateUserMemoryUseCase` → LLM이 패턴 추출 → 새 .md 작성/갱신

---

## 3. Phase 분할

| Phase | 기간 | 일수 | 핵심 |
|-------|------|-----|-----|
| **A** | 5/11(월) ~ 5/19(화) | 9d | 멀티에이전트 재구성 + API 골격 |
| **B** | 5/20(수) ~ 5/27(수) | 8d | API 라우터 + Frontend 4화면 |
| **C** | 5/28(목) ~ 5/31(일) | 4d | GCP 배포 + Polish + 데모 |

---

## 4. Phase A — 멀티에이전트 재구성 + API 골격 (5/11~5/19)

### 4.1 멤버별 일정

#### 신정혜 (Main Orchestrator + Workflow Composer + LLM base)
- 5/12-13: ai_agent 디렉토리 재구성, Composer use case 이동, Main Orchestrator scaffold, Modal app template 작성
- 5/12 저녁: **Modal Gemma 4 + BGE-M3 배포 (`llm-base` app)** — 본인 경험 활용, 1회 배포 후 안정
- 5/14-16: `agent-composer` + `orchestrator` Modal app 배포 + `LLMAdapter`/`EmbeddingAdapter` 작성, LangGraph supervisor 패턴 구현
- 5/17-18: Orchestrator integration test, sub-agent HTTP 호출 검증
- 5/19: Phase A 게이트

#### 박아름 (Skills Builder + nodes_graph 정리)
- 5/12 09:00 sync: doc_parser/Skills Builder/nodes_graph 인터페이스 (김진형과 30분)
- 5/12 오후 sync: inter-agent 통신 계약 (신정혜·햄햄과 1시간)
- 5/12-13: nodes_graph integration test + node_definitions seed 갱신
- 5/14-15: 산업 default seed 5개 작성 (제조/서비스/도소매/음식점/IT)
- 5/16-18: `BuildFromSOPUseCase` + `BuildFromIndustryDefaultUseCase` 구현, `agent-skills-builder` Modal 배포
- 5/19: Phase A 게이트

#### 햄햄(이가원) (Personalization + toolset)
- 5/12 오후 sync: inter-agent 통신 계약
- 5/12-13: toolset connectors 1차 (Slack, HTTP)
- 5/14: `PersonalMemoryStore` Port + GCS 어댑터 (`memory/gcs_memory_store.py`)
- 5/15-16: Personalization use cases (`LoadUserMemory`/`UpdateUserMemory`/`RecallPersonalSkills`), memory.md 포맷 정의
- 5/17: toolset connectors 2차 (Gmail, Sheets)
- 5/18: `agent-personalization` Modal 배포 + integration test
- 5/19: Phase A 게이트

#### 김진형 (doc_parser SSOT + 데모 준비)
- 5/12 09:00 sync: Skills Builder 인터페이스 (박아름과)
- 5/12-13: doc_parser SSOT 이관 (`Chunk`/`ChunkingStrategy`/`QualityGateResult`/`QualityMetrics`/`WarningInfo` → common_schemas)
- 5/14-15: import path 일괄 변경 + 회귀 테스트
- 5/16-17: 데모 시나리오 5개 초안 작성
- 5/18-19: frontend document viewer 일찍 착수 (페어로 박아름·햄햄 지원)

#### 황대원 (api_server 골격 + 인프라 베이스)
- 5/12 오전: Modal workspace 셋업 + 멤버 권한 추가 (30분)
- 5/12-13: api_server FastAPI 골격 + DI 컨테이너
- 5/14: JWT 미들웨어 + 에러 핸들러
- 5/15: pydantic2ts TypeScript 코드젠 + Tailwind/shadcn 베이스 + 색상 토큰 (frontend 공통)
- 5/16-17: SSE manager + `/health`/`/auth` 라우터
- 5/18: ai_agent Main Orchestrator 통합 인터페이스 합의 (신정혜와)
- 5/19: Phase A 게이트, `feature/req-011-infra` 브랜치 baseline 작성 시작

### 4.2 Phase A 게이트 (5/19)
- 5개 Modal app 전부 배포 완료, sub-agent HTTP 호출 정상
- `orchestrator` ↔ `composer`/`skills-builder`/`personalization` 라우팅 동작
- api_server `/health`, `/auth` 라우터 + JWT 검증 동작
- common_schemas TypeScript 산출물 존재
- 모듈별 unit + integration test 통과
- doc_parser SSOT 이관 + 회귀 테스트 통과

---

## 5. Phase B — API 라우터 + Frontend (5/20~5/27)

### 5.1 멤버별 일정

#### 신정혜 — frontend chat + Orchestrator 통합
- 5/20-21: chat 컴포넌트 + SSE 9종 프레임 렌더링
- 5/22-23: chat ↔ Orchestrator HTTP 통합
- 5/24-25: 슬롯 필링 UI + draft spec delta 표시
- 5/26-27: 통합 테스트

#### 박아름 — frontend canvas + workflows 라우터
- 5/20-22: React Flow canvas + 36 노드 표현 + 드래그/연결
- 5/23-24: api_server `/workflows` CRUD + `/validate` 라우터
- 5/25-26: Skills Builder UI 통합 (document viewer에 버튼)
- 5/27: 통합 테스트

#### 햄햄(이가원) — frontend execution + personal skills UI
- 5/20-22: execution monitoring (SSE 실행 진행상황)
- 5/23-24: personal skills 미리보기/편집 UI (memory.md 사용자 노출)
- 5/25-26: toolset 추가 connectors (필요시)
- 5/27: 통합 테스트

#### 김진형 — frontend document viewer + 데모
- 5/20-22: document viewer + 업로드 UI + 파싱 결과 표시
- 5/23-24: Skills Builder 입력 UI 통합
- 5/25: 데모 시나리오 5개 확정
- 5/26-27: 데모 리허설

#### 황대원 — SSE 라우터 + 프론트엔드 공통 + Terraform 착수
- 5/20-22: `/agents/sessions`, `/agents/.../stream`, `/executions/{id}` SSE 라우터
- 5/23: Zustand 스토어 + API client + `useSSEStream` hook
- 5/24-25: Terraform 모듈 작성 (`feature/req-011-infra` 브랜치) — Cloud Run × 3, Cloud SQL, Memorystore, Secret Manager, VPC Connector, IAM
- 5/26-27: GitHub Actions deploy 워크플로우

### 5.2 Phase B 게이트 (5/27)
- 로컬 docker-compose에서 e2e 데모 시나리오 5개 통과
- 4개 화면 모두 동작 (Canvas + Chat + Execution + Document)
- SSE 스트림 9종 프레임 전부 렌더링

---

## 6. Phase C — GCP 배포 + Polish (5/28~5/31)

| 날짜 | 작업 | 담당 |
|------|------|------|
| 5/28(목) | Terraform apply: Cloud SQL + Memorystore + Secret Manager + VPC | 황대원 + 박아름 |
| 5/28(목) | Modal 프로덕션 검증 + 부하 테스트 | 신정혜 + 햄햄 |
| 5/28(목) | 데모 시나리오 검증 (local) | 김진형 |
| 5/29(금) | Cloud Run 배포 + 도메인 연결 + IAM | 황대원 + 박아름 |
| 5/29(금) | 클라우드 환경 e2e 검증 | 팀 전원 |
| 5/30(토) | 버그 픽스 buffer day | 팀 전원 |
| 5/31(일) | 데모 리허설 + 발표 자료 마감 | 팀 전원 |

---

## 7. 멤버별 총 부담

| 담당자 | 일수 | 핵심 작업 |
|--------|-----|----------|
| 황대원 | 13d | api_server core + frontend 공통 + Terraform(`feature/req-011-infra`) + CI/CD + Modal workspace |
| 박아름 | 11.5d | nodes_graph + **Skills Builder Agent** + frontend canvas + workflows 라우터 |
| 신정혜 | 12d | **Main Orchestrator + Workflow Composer + LLM base** + frontend chat |
| 햄햄(이가원) | 10d | toolset + **Personalization Agent (memory.md GCS)** + frontend execution |
| 김진형 | 6d | doc_parser SSOT + frontend document + 데모 시나리오 |

---

## 8. 핵심 마일스톤

| 일자 | 게이트 |
|-----|-------|
| 5/12 09:00 | doc_parser ↔ Skills Builder ↔ nodes_graph 인터페이스 sync (박아름·김진형) |
| 5/12 오후 | inter-agent 통신 계약 schema 확정 (신정혜·박아름·햄햄) |
| 5/12 저녁 | Modal Gemma 4 + BGE-M3 배포 완료 (신정혜) |
| 5/13 | api_server `/health` 동작 |
| 5/15 | Tailwind/shadcn 베이스 commit → frontend 작업자들 fork |
| **5/19** | **Phase A 게이트** — 5개 Modal app + API 골격 동작 |
| 5/22 | `useSSEStream` hook 배포 → 모든 frontend 화면이 SSE 사용 가능 |
| **5/27** | **Phase B 게이트** — 로컬 docker-compose e2e 통과 |
| 5/29 | GCP Cloud Run 배포 + 외부 도메인 접속 가능 |
| **5/31** | **최종 데모** |

---

## 9. 일일 운영

- 매일 09:00 standup (15분)
- Phase 게이트 일(5/19, 5/27)은 오후 2시간 통합 검증
- PR 24시간 룰 (같은 날 리뷰 끝내기)
- 5/12 standup은 30분 확장 (멀티에이전트 인터페이스 합의가 cross-cutting)

---

## 10. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|-------|------|------|
| 신정혜 11d (Main+Composer+LLM base+Modal+Frontend chat) 임계 부담 | Phase A 게이트 슬립 | 5/12 저녁 Modal 배포 슬립 시 김진형이 5/18-19 페어 지원 |
| Modal app 5개 셋업 비용 | Phase A 초반 지연 | Modal app template 5/12-13 신정혜가 1개 작성 후 나머지 멤버는 fork |
| Skills Builder 산업 default 도메인 지식 부족 | 5/14-15 작업 슬립 | 박아름이 stakeholder 인터뷰 또는 ChatGPT로 1차 초안 빠르게 |
| Inter-agent HTTP 통신 분산 디버깅 | 통합 단계 디버깅 시간 ↑ | OpenTelemetry trace 헤더 5/12 계약에 포함, 모든 sub-agent 통과 시 trace_id 전파 |
| Terraform Cloud Run + Cloud SQL 처음 작성 | Phase C 슬립 | 황대원이 Phase B 후반(5/24-25)부터 미리 작성 시작 |
| 5/30(토) buffer 작업일 가용성 | 폴리시 부족 | 사전에 팀원 가용 확인 + 5/29 끝에 남은 작업 우선순위 합의 |

---

## 11. v2 (Sprint 4+) 미루기 항목

- LLM 자유 생성 기반 산업 default (Sprint 3는 seed 5개로 한정)
- Personalization Agent의 능동 학습 (Sprint 3는 워크플로우 완료 시점에만 갱신)
- Modal app 간 mTLS 인증 (Sprint 3는 VPC 내부 통신만)
- 워크플로우 버전 관리, A/B 테스트, 실행 히스토리 검색

---

## 12. 브랜치 전략

| 브랜치 | 용도 | 담당 |
|--------|------|------|
| `feature/req-004-ai-agent` | 멀티에이전트 재구성 | 신정혜 |
| `feature/req-003-skills-builder` 또는 `feature/req-004-skills-builder` | Skills Builder Agent | 박아름 |
| `feature/req-004-personalization` | Personalization Agent | 햄햄 |
| `feature/req-005-toolset` | toolset connectors | 햄햄 |
| `feature/req-006-doc-parser` | SSOT 이관 | 김진형 |
| `feature/req-009-api-server` | api_server 라우터 | 황대원 |
| `feature/req-010-frontend` | frontend 4화면 | 팀 분담 |
| `feature/req-011-infra` | Terraform + Modal workspace | 황대원 |
