# Architecture Decision Records (ADR)

> 설계 결정의 **배경과 맥락**을 남기는 문서.
> 개별 ADR은 [`adr/`](./adr/) 하위에 `ADR-NNNN-slug.md` 형식으로 작성하고, 본 파일은 **인덱스**로만 사용한다.

## 작성 규칙

1. 새 결정은 `adr/ADR-NNNN-slug.md` 파일로 추가 (NNNN은 4자리 zero-padded, 1부터 순차).
2. 기존 결정을 **뒤집는** 경우: 원본 ADR에 `Superseded by ADR-NNNN` 표기 + 새 ADR 추가. **삭제 금지**.
3. 본 인덱스에 `Status / Title / Date` 한 줄을 추가한다.
4. 템플릿: [`adr/ADR-0000-template.md`](./adr/ADR-0000-template.md) 복사 후 작성.

## Status 정의

- `Proposed` — 검토 중
- `Accepted` — 적용됨 (현행)
- `Deprecated` — 더 이상 권장되지 않음 (대체 없음)
- `Superseded` — 다른 ADR로 대체됨

## Index

| # | Title | Status | Date |
|---|-------|--------|------|
| 0001 | [브랜치-per-모듈에서 모노레포 구조로 전환](./adr/ADR-0001-monorepo-structure.md) | Accepted | 2026-05-03 |
