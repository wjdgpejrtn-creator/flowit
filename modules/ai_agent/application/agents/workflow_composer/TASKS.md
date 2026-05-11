# Workflow Composer Agent — 작업 명세

**담당자**: 신정혜
**Modal app**: `agent-composer`

## 목적

사용자 채팅 메시지를 받아 13-노드 LangGraph 파이프라인으로 워크플로우 초안 작성.
기존 `ComposeWorkflowUseCase` + `ContinueConversationUseCase`를 sub-agent 형태로 재구성.

## 인터페이스

입력: `AgentRequest` (state 안에 user message, personal_memory 포함)
출력: `AsyncGenerator[SSEFrame]` (RationaleDeltaFrame, SlotFillQuestionFrame,
       DraftSpecDeltaFrame, ResultFrame 등)

## Work items

- [ ] 이동된 `compose_workflow_use_case.py` / `continue_conversation_use_case.py`
      를 sub-agent 패턴에 맞게 리팩터링 — `AgentRequest`/`AgentResponse` I/O 적용
- [ ] 13-노드 LangGraph StateGraph 유지 (security → intent → retriever → drafter →
      validator → qa_evaluator → promote)
- [ ] `LLMPort` 어댑터를 `llm-base` Modal endpoint 호출로 교체
- [ ] personal_memory를 prompt context에 주입 (DrafterService 확장)
- [ ] Modal app 작성 (`adapters/modal/composer_app.py`)
- [ ] Modal 배포
- [ ] 기존 unit 테스트 회귀 0건 (import path 변경 반영)

## 의존성

- `llm-base` Modal endpoint (5/12 저녁 신정혜 본인 배포)
- `EmbeddingPort` adapter (BGE-M3, retriever_node가 사용)
- `nodes_graph.NodeRegistry` (retriever_node가 노드 후보 검색)

## 완료 기준

- 사용자 메시지 → 워크플로우 초안 SSE 스트림 동작
- personal_memory 주입 시 prompt 변화 검증 (테스트)
- Phase A 게이트 통과
