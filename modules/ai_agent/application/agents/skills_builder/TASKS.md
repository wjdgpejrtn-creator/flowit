# Skills Builder Agent — 작업 명세

**담당자**: 박아름
**Modal app**: `agent-skills-builder`

## 목적

회사 내부 SOP 문서(doc_parser 출력) 또는 산업 표준 default를 받아
nodes_graph의 NodeDefinition으로 변환 → 사용자 워크스페이스의 skills 카탈로그에 등록.

## 인터페이스

입력: `AgentRequest` (state.input_type = "sop_document" | "industry_default",
                     state.payload = DocumentBlock | IndustryCode)
출력: `AsyncGenerator[SSEFrame]` (생성 진행 상황 + 최종 NodeDefinition 목록)

## Work items

- [ ] `BuildFromSOPUseCase.execute()` 구현
  - DocumentBlock 입력 → LLM으로 단계별 작업 추출 → NodeDefinition 변환
  - nodes_graph.NodeDefinitionRepository.save() 호출
- [ ] `BuildFromIndustryDefaultUseCase.execute()` 구현
  - IndustryCode (제조/서비스/도소매/음식점/IT) → seed에서 NodeDefinition 로드
- [ ] 산업 default seed 5개 작성 (`database/seeds/industry_defaults/`)
  - 각 산업당 핵심 워크플로우 노드 5~10개
- [ ] Modal app 작성 (`adapters/modal/skills_builder_app.py`)
- [ ] Modal 배포
- [ ] integration test: 샘플 SOP 문서 → 노드 등록 검증

## 의존성

- `doc_parser` 출력 schema (DocumentBlock, ContentBlock)
- `nodes_graph.NodeDefinitionRepository` (storage 구현체)
- `llm-base` Modal endpoint
- `agent_protocol.py` schema

## 완료 기준

- 샘플 SOP 1건 입력 → NodeDefinition 3개 이상 생성 + DB 저장
- 산업 default 5개 seed 적용 후 IndustryCode로 조회 가능
- Phase A 게이트 통과
