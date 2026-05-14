# Main Orchestrator Agent — 작업 명세

**담당자**: 신정혜
**Modal app**: `orchestrator`
**브랜치**: `feature/req-004-ai-agent` 또는 sub-branch

## 목적

3개 sub-agent(Workflow Composer, Skills Builder, Personalization)를 LangGraph
supervisor 패턴으로 라우팅하고, 세션 단위로 personal memory를 로드해 state에 주입.

## 인터페이스

입력: `common_schemas.agent_protocol.AgentRequest`
출력: `AsyncGenerator[SSEFrame]` (transport.py 9종 프레임)

## Work items

- [ ] LangGraph StateGraph 정의 (supervisor 패턴)
  - 노드: classify_intent → load_personal_memory → route → invoke_sub_agent → aggregate
- [ ] sub-agent HTTP 클라이언트 (httpx, VPC 내부 endpoint 호출)
  - composer_url, skills_builder_url, personalization_url 환경변수로 주입
- [ ] `RouteRequestUseCase.execute()` 구현 (skeleton 채우기)
- [ ] OpenTelemetry trace_id 전파 (모든 sub-agent 호출 헤더에 포함)
- [ ] Modal app 작성 (`adapters/modal/orchestrator_app.py`, template fork)
- [ ] Modal 배포 (`modal deploy adapters/modal/orchestrator_app.py`)
- [ ] integration test: 3개 sub-agent stub으로 라우팅 흐름 검증

## 의존성

- `agent_protocol.py` schema 확정 (5/12 오후 sync)
- Workflow Composer / Skills Builder / Personalization Modal endpoint URL
- `llm-base` Modal endpoint URL

## 완료 기준

- 세션 시작 → personal memory 로드 → composer 호출 → 결과 SSE 스트림 동작
- trace_id 전파 검증 (3개 sub-agent 로그에서 동일 trace_id 확인)
- Phase A 게이트(5/19) 통과

## 참조

- `docs/specs/plan/sprint-3.md` §2.4 inter-agent 통신 계약
- `_agent_templates/ORCHESTRATOR.md`
