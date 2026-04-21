# Project MAP

> 프로젝트 최상위 폴더/브랜치 지도. **상위 구조 지도**이지 파일 인덱스가 아니다.
> 새 최상위 폴더나 브랜치가 생길 때만 갱신한다.

## 최상위 구조

```
Workflow_Automation/
├── _agent_templates/     # 브랜치 체크아웃 시 agents/ 로 복사되는 에이전트 템플릿
├── _claude_templates/    # 브랜치별 CLAUDE.md 템플릿
├── .githooks/            # post-checkout 스캐폴딩 훅
├── .github/              # PR 템플릿, 워크플로우
├── .claude/              # Claude Code 로컬 설정
├── docs/
│   └── context/          # 공용 지식 베이스 (이 위키) — docs 브랜치에서만 편집
└── README.md
```

## 코드 브랜치 (예정)

| 브랜치 | 최상위 경로 | 역할 |
|--------|-------------|------|
| `API_Server` | `API_Server/` | FastAPI 서버 |
| `Database` | `Database/` | 스키마/마이그레이션/Repository |
| `Execution_Engine` | `Execution_Engine/` | 노드 런타임/디스패처/Agent |
| `Frontend` | `Frontend/` | React/Next.js UI |
| `docs` | `docs/context/` | 본 위키 (코드 편집 금지) |

각 브랜치의 내부 폴더 규칙은 `.githooks/post-checkout` 스캐폴딩과 해당 브랜치의 `CLAUDE.md`를 따른다.

## 관련 문서

- 아키텍처: [`architecture.md`](./architecture.md)
- 설계 결정: [`decisions.md`](./decisions.md)
