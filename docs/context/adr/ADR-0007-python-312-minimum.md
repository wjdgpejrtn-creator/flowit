# ADR-0007: Python 최소 버전 3.12로 상향

- **Status**: Accepted
- **Date**: 2026-05-05
- **Deciders**: @dhwang0803-glitch
- **Tags**: area/infra, area/common_schemas

## Context

프로젝트 초기에는 Python >=3.11을 최소 버전으로 설정했으나, 프로덕션 인프라 결정 사항이 구체화되면서 재검토가 필요해졌다.

- **Modal GPU 런타임**: REQ-004 LLM inference에 사용할 Modal은 Ubuntu 24.04 기반 이미지를 제공하며, 이 환경은 Python 3.12에 최적화되어 있다.
- **GCP Cloud Run**: 프로덕션 배포 대상인 Cloud Run의 공식 Python 이미지도 3.12를 기본으로 제공한다.
- **3.12 언어 기능 활용**: f-string 중첩, `type` 문, 향상된 에러 메시지 등 DX 개선 요소를 팀 전체가 활용 가능.

## Decision

**모든 패키지와 서비스의 `requires-python`을 `>=3.12`로 통일한다.**

적용 범위:
- `packages/common_schemas/python/pyproject.toml`
- `.github/workflows/codegen-drift.yml` (CI Python 버전)
- 향후 추가되는 모든 `pyproject.toml` / `Dockerfile`

## Consequences

### Positive
- Modal / Cloud Run / CI 환경 간 Python 버전 불일치 제거
- 3.12 전용 문법·표준 라이브러리(tomllib 등) 안전하게 사용 가능
- 의존 라이브러리(Pydantic v2, FastAPI, SQLAlchemy 2.x)가 모두 3.12 호환 확인됨

### Negative / Trade-offs
- 팀원 로컬 환경이 3.11인 경우 업그레이드 필요 (pyenv/conda로 대응 가능)
- 일부 레거시 패키지가 3.12 미지원일 경우 대안 검토 필요 (현재 해당 없음)

### Follow-ups
- 각 팀원 로컬 Python 버전 확인 및 업그레이드 안내
- 향후 Dockerfile 작성 시 `python:3.12-slim` 베이스 이미지 사용

## Alternatives Considered

- **Python >=3.11 유지**: Modal/Cloud Run 기본 환경과 불일치, CI에서 별도 버전 관리 부담
- **Python >=3.13**: 아직 안정화 초기 단계, 주요 라이브러리 호환성 불확실

## References

- PR #11: `docs: 11개 모듈 구현 명세 + Python 3.12 최소 버전`
- Modal docs: Ubuntu 24.04 image defaults
- Cloud Run Python runtime documentation
