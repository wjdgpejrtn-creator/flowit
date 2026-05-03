# ADR-0001: 브랜치-per-모듈에서 모노레포 구조로 전환

- **Status**: Accepted
- **Date**: 2026-05-03
- **Deciders**: @dhwang0803-glitch (조장)
- **Tags**: area/architecture, area/infrastructure, area/branching

## Context

Baseline v1.0 (2026-04-30) 확정 후, 12개 REQ 문서와 4계층 마이크로서비스 아키텍처를 코드 저장소에 반영해야 했다.

기존 방식은 **브랜치-per-모듈**(API_Server, Database, Execution_Engine, Frontend 등 각각 독립 브랜치)이었으며, `post-checkout` Git hook이 브랜치 생성 시 자동으로 폴더 구조와 CLAUDE.md를 스캐폴딩했다.

이 방식의 문제점:

1. **스키마 불일치 위험**: REQ-012(Common Schemas)의 Pydantic v2 → TypeScript 타입이 여러 브랜치에 분산되어 동기화 보장 불가
2. **원자적 변경 불가**: API 스키마 변경 시 api-server·frontend·common-schemas를 각 브랜치에서 별도 PR로 처리해야 함
3. **코드 리뷰 파편화**: 서비스 간 영향도를 단일 diff로 확인 불가
4. **CI/CD 복잡성**: 브랜치 간 의존성 관리에 별도 오케스트레이션 필요
5. **12개 REQ × 6명 협업**: 상호 의존 관계(modules → services → packages)가 브랜치 경계를 넘어감

## Decision

**단일 모노레포 구조**를 채택하고, 브랜치-per-모듈 방식을 폐기한다.

### 디렉토리 구조 (5개 최상위)

| 디렉토리 | 역할 | 대응 REQ |
|---|---|---|
| `packages/` | 공유 패키지 (common-schemas) | REQ-012 |
| `services/` | 배포 가능 서비스 (api-server, execution-engine, frontend) | REQ-007, 009, 010 |
| `modules/` | 도메인 모듈 (auth, nodes-graph, ai-agent, toolset, doc-parser, storage) | REQ-002~006, 008 |
| `database/` | PostgreSQL 스키마·마이그레이션 | REQ-001 |
| `infra/` | Terraform + Docker | REQ-011 |

### 브랜치 전략

| 브랜치 | 용도 |
|---|---|
| `main` | 안정 브랜치 (protected, PR only) |
| `development` | 통합 브랜치 — 모든 feature PR의 base |
| `feature/req-XXX-*` | REQ 단위 기능 개발 (development에서 분기) |
| `release` | 프로덕션 배포 트리거 |
| `docs` | 문서 전용 |

### import 규칙

- `services/*` → `modules/*` → `packages/*` 방향만 허용
- 역방향 import 금지 (순환 의존 방지)
- `database/`는 순수 SQL, 코드 의존 없음

## Consequences

### Positive

- **타입 안전성**: `packages/common-schemas`를 Python·TypeScript 모두 단일 소스에서 참조
- **원자적 변경**: API 변경 + 프론트 대응을 하나의 PR로 처리 가능
- **CI 효율**: 변경 경로 기반 선택적 빌드 (`paths` 필터)
- **코드 리뷰**: 서비스 간 영향도를 단일 diff로 확인
- **Onboarding**: 새 팀원이 전체 구조를 한눈에 파악 가능

### Negative / Trade-offs

- **기존 스캐폴딩 훅 무효화**: `.githooks/post-checkout`의 브랜치별 자동 생성 로직이 더 이상 작동하지 않음
- **`_claude_templates/`의 브랜치별 CLAUDE.md**: 모노레포에서는 디렉토리별 가이드로 전환 필요
- **대규모 초기 변경**: 79개 파일 신규 생성, 기존 docs 구조 갱신
- **머지 충돌 가능성**: 여러 REQ가 같은 모듈을 동시에 수정할 경우 충돌 빈도 증가

### Follow-ups

- [ ] `.githooks/post-checkout` 훅을 모노레포 방식에 맞게 수정 또는 폐기
- [ ] `_claude_templates/`를 디렉토리별 CLAUDE.md로 전환 검토
- [ ] GitHub branch protection 규칙 설정 (development, release)
- [ ] CI workflow (`ci.yml`) 변경 감지 기반 paths 필터 구현

## Alternatives Considered

- **Option A: 브랜치-per-모듈 유지** — 기존 post-checkout 훅 활용, 각 브랜치 독립 개발. 기각 사유: REQ-012 Common Schemas의 SSOT 보장 불가, 원자적 변경 불가, 6명 협업 시 통합 비용 과다
- **Option B: 멀티레포 (서비스별 별도 저장소)** — 완전한 격리, 독립 배포. 기각 사유: MVP 단계에서 관리 오버헤드 과다, 공유 스키마 동기화 파이프라인 별도 구축 필요, 팀 규모(6명) 대비 비효율
- **Option C: 모노레포 + Nx/Turborepo 빌드 시스템** — 모노레포에 전용 빌드 오케스트레이터 추가. 기각 사유: Python + TypeScript 혼합 스택에서 도구 성숙도 부족, 학습 비용 대비 MVP 기간(2주) 내 ROI 낮음

## References

- [Baseline v1.0 요구사항 통합 명세](https://www.notion.so/3523a18a300981fda314e5d498e2a285)
- [`MONOREPO_STRUCTURE.md`](../../../MONOREPO_STRUCTURE.md) (루트 구조 문서)
- 커밋: `chore: 모노레포 구조 초기화 (Baseline v1.0 기반)`
