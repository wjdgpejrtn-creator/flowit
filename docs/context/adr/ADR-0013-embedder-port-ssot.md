# ADR-0013: EmbedderPort SSOT — nodes_graph 소유 + ai_agent 구현체 (예외 패턴)

- **Status**: Accepted
- **Date**: 2026-05-12 (결정), 2026-05-15 (공식 ADR 등록 + REQ-004 spec / plan / CLAUDE.md 정합 완성)
- **Deciders**: @billionaireahreum (박아름), @dhwang0803-glitch (조장 후속 확인)
- **Tags**: area/nodes_graph, area/ai_agent, layer/domain, layer/adapter, ssot, dip

## Context

REQ-003 spec과 REQ-004 spec이 5월 초 작성될 때 임베딩 Port를 별개로 명시했다.

- **REQ-003 spec** (박아름 영역, 5월 초): `nodes_graph/domain/ports/embedder_port.py` — `EmbedderPort` ABC
  - 용도: 카탈로그 노드 임베딩 (Skills Builder + nodes_graph SearchNodesUseCase + RegisterNodesUseCase)
  - 시그니처: `embed(text: str) -> list[float]`, `embed_batch(texts: list[str]) -> list[list[float]]`
- **REQ-004 spec** (신정혜 영역, 5월 초 + 5/11 황대원 ADR): `ai_agent/domain/ports/embedding_port.py` — `EmbeddingPort` ABC (별개 신설 명시)
  - 용도: ai_agent 내 임베딩 (Composer + Personalization)
  - 시그니처: `embed(text: str) -> list[float]`

두 Port 인터페이스가 사실상 동일(BGE-M3 768d 텍스트 임베딩 호출)이지만 별개 정의된 상태로 5/12 신정혜 PR #39 (ModalLLMAdapter + ModalEmbeddingAdapter 구현) 머지 시점에 도달했다.

### 발견된 문제 — 의존성 역전 위반

`EmbeddingPort`를 ai_agent에 두면 다음 의존성 방향이 발생한다.

- **nodes_graph.SearchNodesUseCase** / **RegisterNodesUseCase** — 카탈로그 노드 임베딩 필요 → `ai_agent.EmbeddingPort` 사용 필요
- → **nodes_graph → ai_agent** 의존 발생
- CLAUDE.md "modules 간 허용된 교차 import" 표에 `nodes_graph → ai_agent` 라인 **없음** = 의존성 방향 위반

Clean Architecture 의존성 역전 원칙(DIP)에 따라 안쪽 도메인(nodes_graph 카탈로그)이 인터페이스를 정의해야 하고, 바깥쪽(ai_agent Modal 어댑터)이 구현체를 제공해야 한다.

## Decision

**EmbedderPort SSOT를 nodes_graph 소유로 통일한다.** 1개 Port 1개 SSOT.

### 구체적 결정

1. **Port ABC 정의 위치**: `modules/nodes_graph/domain/ports/embedder_port.py` (박아름 영역)
2. **구현체 위치**: `modules/ai_agent/adapters/llm/modal_embedding_adapter.py` (신정혜 영역, Modal Gemma+BGE-M3 호스팅 영역)
3. **`ai_agent/domain/ports/embedding_port.py` 신설 폐기**: REQ-004 spec 본래 명시했던 `EmbeddingPort`는 별도 신설하지 않음
4. **사용처**:
   - nodes_graph 영역 — `nodes_graph.domain.ports.embedder_port.EmbedderPort` 직접 import
   - ai_agent 영역 (Composer + Personalization + Skills Builder) — `nodes_graph.domain.ports.embedder_port.EmbedderPort` 직접 import (CLAUDE.md 교차 import 표 line 138 `ai_agent → nodes_graph/domain/ports` 정합)
   - storage / api_server 영역 — composition root에서 DI 주입

### 예외 패턴 명시

본 결정은 일반 Port → Adapter 매핑 패턴의 예외이다.

- **일반 패턴**: Port ABC와 구현체가 같은 모듈 내부 (예: `auth.CipherPort` → `auth/adapters/cipher/`)
- **EmbedderPort 예외 패턴**: Port ABC는 nodes_graph 소유, 구현체는 ai_agent 소유 (Modal GPU 호출은 ai_agent 영역이라 구현체만 이전, Port는 의존성 방향 위반 방지 위해 nodes_graph 보존)

CLAUDE.md "Port → Adapter 매핑" 표에 예외 패턴 1줄 주석 명시 (PR #69로 반영 완료).

## Alternatives Considered

### Alternative 1: ai_agent에 EmbeddingPort 별개 신설 (REQ-004 spec 본래 의도)

- 장점: spec/plan 본래 명시대로 영역 분리
- 단점: nodes_graph 영역 Use Case가 ai_agent에 의존 → 의존성 방향 위반
- → **2026-05-12 박아름 분석 + 조장 PR #54 embedder_port shim revert 요청으로 폐기**

### Alternative 2: 두 Port 별개 운영 (인터페이스 동일하지만 영역 분리)

- 장점: 영역별 책임 명확
- 단점: 인터페이스 100% 동일(`embed(text) -> list[float]`)인 Port 2개 = SSOT 위반, 코드 중복
- → 명확한 비용 대비 이득 없음 → 폐기

### Alternative 3: ai_agent SSOT (모든 모듈이 ai_agent.EmbeddingPort 사용)

- 장점: 구현체와 Port가 같은 모듈
- 단점: nodes_graph → ai_agent 의존 = 의존성 역전 위반
- → 조장 PR #54 revert 요청 시 동일 이유로 폐기

## Consequences

### Positive

- **의존성 방향 정합**: nodes_graph → ai_agent 의존 차단 ⇒ Clean Architecture DIP 준수
- **SSOT 1개**: EmbedderPort 단일 Port → 박아름 5/12 결정 시점에 코드 7곳 일관 정합
- **Modal 호스팅 책임 분리**: 신정혜 ai_agent 영역에 Modal Gemma+BGE-M3 구현체 캡슐화

### Negative

- **예외 패턴**: 일반 Port → Adapter 매핑(같은 모듈 내부)과 다른 변형이라 신규 멤버 onboarding 시 주의 필요 → CLAUDE.md "Port → Adapter 매핑" 표에 예외 1줄 주석으로 mitigated
- **5월 초 spec 본래 의도(2 Port 별개)와 차이**: REQ-004 spec / plan / decisions.md(이번 ADR-0013)로 일괄 정합 → 5/15 박아름 PR #69 + 후속 commit으로 완성

## Implementation Status

### 코드 적용 (5/12 박아름 결정 시점)

- ✅ `modules/nodes_graph/domain/ports/embedder_port.py` — Port ABC 보존
- ✅ `modules/ai_agent/adapters/llm/modal_embedding_adapter.py` — `EmbedderPort` 구현 (docstring 명시)
- ✅ `modules/ai_agent/adapters/node_registry_adapter.py` + Skills Builder 3 use cases — `nodes_graph.EmbedderPort` 사용
- ❌ `modules/ai_agent/domain/ports/embedding_port.py` — **신설하지 않음** (PR #71에서 신설 시도 → 본 ADR 근거로 revert 요청)

### 문서 정합 (5/15 PR #69 + 후속 commit)

- ✅ CLAUDE.md "Port → Adapter 매핑" 표 (line 178) — `EmbedderPort` 예외 패턴 명시
- ✅ MONOREPO_STRUCTURE.md (line 99, 408) — 정합
- ✅ docs/context/clean_architecture.md (line 363, 1274, 1510) — 정합
- ✅ docs/specs/REQ-004-ai-agent.md (line 95, 148, 149, 161, 323, 442, 508) — 본 commit으로 정합 완성
- ✅ docs/specs/plan/sprint-3.md (line 55, 186, 210, 240, 429) — 본 commit으로 정합 완성

### 후속 작업

- 햄햄 PR #71에서 `ai_agent/domain/ports/embedding_port.py` 신설 부분 revert 필요 (4곳)
  - 본 ADR을 근거로 박아름이 PR #71 코멘트로 revert 요청 게시 (https://github.com/billionaireahreum/Workflow_Automation/pull/71#issuecomment-4457159938)

## References

- 박아름 5/12 결정 메모리 (`feedback_embedder_dimension`, `project_skills_builder_customization_v2`)
- PR #30 nodes_graph 카탈로그 30종 구현 (5/9 머지) — `EmbedderPort` 보존
- PR #39 ModalLLMAdapter + ModalEmbeddingAdapter (5/12 머지) — `EmbedderPort` 구현체
- PR #54 (햄햄 Personalization Agent, OPEN) — 조장이 embedder_port shim revert 요청 (본 ADR 근거 초기 발견 시점)
- PR #69 (박아름 docs PR, OPEN) — CLAUDE.md / REQ-004 spec / MONOREPO_STRUCTURE / clean_architecture 정합 정정
- PR #71 (햄햄 PHASE 1, OPEN) — `EmbeddingPort` 신설 4곳 revert 요청 진행 중
- verification 보고서 `modules/ai_agent/report/2026-05-14-verification-auth-node-skillbuilder.md` §1.5 / §9.1
