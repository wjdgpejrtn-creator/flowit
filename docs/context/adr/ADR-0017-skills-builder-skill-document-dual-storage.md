# ADR-0017: Skills Builder 산출물 = NodeDefinition + SkillDocument 이중 저장 (`skills_marketplace` = 사내 SkillsMP 역할)

- **Status**: Proposed
- **Date**: 2026-05-20
- **Deciders**: @dhwang0803-glitch (조장, REQ-001/008/009/skills_marketplace) + @billionaireahreum (박아름, REQ-002/003/004 Skills Builder)
- **Tags**: area/skills_builder, area/skills_marketplace, layer/domain, layer/storage

## Context

REQ-004 Skills Builder의 산출물 형식과 저장 위치가 2026-05-19~05-20 두 차례 카톡 협의에서 명확화됐다.

**1차 (5/19)**: 조장 카톡 — "skills_marketplace를 기존의 [Anthropic] SkillsMP와 동일한 역할을 하도록 하는 것임. Skills Builder는 SkillsMP의 표준 SKILL.md와 같은 것을 레퍼런스로 유사한 산출물을 만들어서 skills_marketplace에 저장하고, main agent가 사용자와 대화하면서 노드를 만들 때 사용자가 만들려고 하는 것과 유사한 것을 옵션으로 사용자에게 skill 문서를 제공"

**2차 (5/19~5/20)**: 박아름 8가지 명확화 카톡 발송 → 조장 답변:
1. `skills_marketplace` 신설 후 별도 테이블 (이번 주말 2026-05-25 예정, ADR-0012 PR-2d)
2. Skills Builder upsert 대상 = `skills_marketplace` (nodes_graph 아님)
3. NodeDefinition = 메타 정의만 / **SkillDocument = 파일이므로 별도 GCS 버킷 저장**
4. Composer 검색 흐름 = 사용자 intent 파악 후 노드 탐색 타이밍에 스킬도 탐색해서 옵션 제공
5. `execution_engine` 기존 JSON 구조 재사용 = `input_schema`/`output_schema` 그대로
6. Skills Builder = 스킬 생성 전용 (5/14 옵션 A 책임 범위 유지)
7. 외부 SkillsMP.com 공유 X, **레퍼런스만**
8. spec REQ-004 갱신 + 신규 ADR PR 박아름 진행

**핵심 기존 상태 (5/20 기준)**:
- Skills Builder 현재 산출물 = `NodeDefinition` (`nodes_graph.NodeDefinitionRepository.upsert`)
- markdown 지침서 필드 부재 — `description` 한 문장만 자연어
- `modules/skills_marketplace/` 모듈 미신설 (ADR-0012 v3 PR-2d 예정)
- SkillsMP 표준 = Anthropic 2025-12 발표 (SKILL.md frontmatter + markdown body), 2026 OpenAI Codex CLI도 채택

## Decision

### 1. `skills_marketplace` = 사내 SkillsMP 역할 (외부 미공유)

`modules/skills_marketplace/`는 외부 SkillsMP.com과 동일한 컨셉(스킬 마켓플레이스)을 사내에서 구현한다. 외부 공유는 하지 않으며 SKILL.md 표준은 **레퍼런스로만 채택**한다.

### 2. Skills Builder 산출물 = `NodeDefinition` + `SkillDocument` 이중 저장

| 산출물 | 형식 | 저장 위치 | 소비자 |
|--------|------|----------|--------|
| `NodeDefinition` (메타) | pydantic + JSON Schema | `skills_marketplace` 테이블 (PostgreSQL) | `execution_engine` (워크플로우 노드 실행) |
| `SkillDocument` (지침서) | markdown frontmatter + body | GCS 버킷 (별도 파일) | Main Agent (사용자 옵션 제시) |

**`NodeDefinition` 필드 (기존 `nodes_graph.NodeDefinition` 재사용)**:
- `node_id`, `node_type`, `name`, `description`, `category`, `version`
- `input_schema`, `output_schema`, `parameter_schema` (JSONB, `execution_engine` 재사용)
- `risk_level`, `required_connections`, `service_type`
- `embedding` (BGE-M3 768d)

**`SkillDocument` 구조 (SkillsMP SKILL.md 레퍼런스)**:
```yaml
---
name: kebab-case-skill-name
description: 자연어 트리거 설명 (LLM이 사용자 의도 매칭 시 참조)
---

# Skill 제목

## When to use this skill
...

## Step-by-step instructions
1. ...
2. ...

## Inputs / Outputs
(NodeDefinition.input_schema/output_schema와 동일 정보, 사람이 읽기 쉬운 형식)
```

GCS 경로 패턴 (안):
```
gs://{SKILLS_MARKETPLACE_BUCKET}/skills/{skill_id}/SKILL.md
gs://{SKILLS_MARKETPLACE_BUCKET}/skills/{skill_id}/scripts/   (선택)
gs://{SKILLS_MARKETPLACE_BUCKET}/skills/{skill_id}/templates/ (선택)
```

### 3. Composer 검색 흐름 갱신 (5/20 조장 확정)

```
사용자 입력
  ↓
IntentAnalyzerService (사용자 intent 파악)
  ↓
Workflow Composer
  ├ NodeRetriever → nodes_graph (기존 노드 카탈로그 검색)
  └ SkillRetriever → skills_marketplace (스킬 동시 탐색, NEW)
  ↓
사용자에게 옵션 제시 (노드 + 스킬 후보)
  ↓
사용자 선택 → 워크플로우 그래프 노드 추가
  ↓
execution_engine 실행 (NodeDefinition.input_schema/output_schema 재사용)
```

### 4. 5/14 옵션 A 책임 범위 유지

Skills Builder = **스킬 생성 전용**. 워크플로우 생성 안 함 (Composer는 신정혜 영역).

### 5. SkillsMP 표준 = 레퍼런스, 외부 공유 X

외부 SkillsMP.com에 우리 스킬 공유 안 함. 미래 외부 공유 결정 시 SKILL.md 표준 디렉토리로 export 가능한 구조로 설계 (frontmatter + markdown body가 SKILL.md 그대로 직렬화 가능).

## Consequences

### Positive

- **사내 SkillsMP 인프라 확보** — 사내 직원이 자기 스킬 생성/공유 가능
- **LLM-friendly 지침서** — `SkillDocument` markdown이 Main Agent에게 자연스러운 input
- **`execution_engine` 변경 0** — `NodeDefinition.input_schema`/`output_schema` 그대로 재사용
- **외부 SkillsMP 호환 가능성** — frontmatter + body 직렬화 시 SKILL.md 그대로 export (미래 옵션)
- **사용자 옵션 제시** — Main Agent가 자연어 description 매칭으로 유사 스킬 추천 가능
- **5/14 옵션 A 정합** — Skills Builder 책임 범위 유지

### Negative / Trade-offs

- **이중 저장 비용** — `NodeDefinition` DB + `SkillDocument` GCS 동시 쓰기, 두 저장소 일관성 관리 필요
- **변환 비용** — Skills Builder가 SkillNode 추출 후 NodeDefinition + SkillDocument 둘 다 생성
- **`modules/skills_marketplace/` 의존** — PR-2d 신설 (이번 주말, 조장 영역) 대기 후 박아름 코드 변경 PR 가능
- **`SkillDocumentStore` Port 신설 필요** — GCS adapter (`ai_agent/adapters/skill_document/` 위치 후보) — 박아름 영역 신규
- **SOP 추출 LLM 프롬프트 갱신** — `BuildFromSOPUseCase`의 LLM이 markdown instructions까지 생성하도록 프롬프트 보강

### Follow-ups

- ⏳ `modules/skills_marketplace/` 신설 (ADR-0012 v3 PR-2d, 조장, 2026-05-25 주말 예정)
- ⏳ Skills Builder 코드 변경 PR (박아름, 모듈 신설 후):
  - `SkillDocument` 모델 신설 (`ai_agent/domain/entities/skill_document.py`)
  - `SkillDocumentStore` Port (`ai_agent/domain/ports/`) + GCS adapter (`ai_agent/adapters/skill_document/gcs_skill_document_store.py`)
  - `BuildFromXxxUseCase` 산출물 변경 — NodeDefinition + SkillDocument 동시 upsert
  - `nodes_graph.NodeDefinitionRepository` → `skills_marketplace.SkillRepository` 의존성 교체
  - seed JSON 갱신 — `instructions` 필드 추가
- ⏳ Composer 검색 흐름 갱신 (신정혜 영역, ADR-0017 적용 시)

## Alternatives Considered

### A. 단일 저장 (DB JSONB 안에 markdown 포함)
- 옵션: `node_definitions.instructions TEXT` 컬럼 추가
- 장점: 마이그레이션 작음, pgvector 검색 그대로
- 단점: 외부 SkillsMP.com export 시 변환 레이어 필요, 파일 시스템 친화 X (git diff/마크다운 에디터 어색)
- **기각 사유** (5/20 조장 확정): 파일이므로 GCS 별도 저장이 정합

### B. SKILL.md 디렉토리만 (DB 폐기)
- 옵션: `skills_marketplace`를 GCS 파일 디렉토리만 사용 (DB 0)
- 장점: 외부 SkillsMP.com 완벽 호환
- 단점: `execution_engine` 호환 깨짐 (JSON Schema 검색/실행 인프라 재설계 필요), 워크플로우 그래프 패러다임과 불일치
- **기각 사유**: 우리 시스템은 워크플로우 그래프 자동화 플랫폼이라 `NodeDefinition` 메타 필수

### C. 본 결정 — 이중 저장 (NodeDefinition DB + SkillDocument GCS)
- ✅ 채택 — 두 패러다임의 장점 결합

## References

- [[project_skillsmp_compatibility_2026_05_19]] — 5/19 조장 카톡 + 박아름 8가지 명확화
- [[project_skills_builder_customization_v2]] — 5/14 옵션 A 책임 범위 결정
- ADR-0012 v3 — `modules/skills_marketplace/` 신설 (PR-2d, 조장)
- ADR-0014 — ToolToNodeWrapper 제거 (박아름 5/19)
- Anthropic Skills 오픈 표준 (2025-12) — SKILL.md frontmatter + markdown body 형식 레퍼런스
- `docs/specs/REQ-004-ai-agent.md` §"application/agents/skills_builder/" — 본 ADR 적용 후 spec 갱신
