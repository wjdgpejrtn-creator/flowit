PR을 정식 3축 기준(Clean Architecture / SSOT spec / 크로스 모듈 안전성)으로 리뷰한다. 인자로 PR 번호(들)를 받는다. 예: `/pr-3axis-review 229` 또는 `/pr-3axis-review 229 232`

---

## 원칙 (예외 없음)

"정식 리뷰" 같은 수식어가 없어도 PR 리뷰 요청이면 **항상 이 3축으로 섹션을 나눠** 점검한다. 자의적 예외 처리 금지:

- **셀프 PR**(작성자=본인): 작은 hotfix라도 3축 적용.
- **Release sync PR**(코드 변경 없는 머지): 축 1·2는 "sync 특성상 N/A" 명시하더라도 **섹션은 유지**. 축 3(release gate / 미해결 PR 의존성 / CI 트리거)은 항상 실측.
- **1파일·소규모 변경**: scope 작아도 3축 섹션 분할. 빈 축은 "위반 없음 ✓" 한 줄.

---

## Step 0. 정확한 diff 확보 (캐시 함정 회피 — 최우선)

`gh pr diff`는 stale 캐시일 수 있으므로 **신뢰하지 않는다.** 반드시 fetch 후 merge-base 기준 실측:

```bash
gh pr view <N> --json number,title,author,baseRefName,headRefName,state,additions,deletions,changedFiles,body,commits
git fetch origin <headRefName> <baseRefName>
# net diff (base와의 merge-base 기준 — 머지 커밋 노이즈 제거)
git diff --stat $(git merge-base origin/<baseRefName> origin/<headRefName>) origin/<headRefName>
git diff $(git merge-base origin/<baseRefName> origin/<headRefName>) origin/<headRefName> -- <파일>
```

**브랜치 staleness 검증**: base가 오래됐으면(100+ 커밋 stale) 머지 충돌·import 깨짐·중복 구현 위험. merge-base가 base tip의 ancestor인지 + 신규 import 대상 파일이 실제 존재하는지 확인.

**참조 정합성**: PR이 새로 import/호출하는 심볼(함수·prop·타입)이 실제로 해당 위치에 존재하는지 `git show origin/<head>:<file>`로 확인.

---

## Step 1. 축 1 — Clean Architecture 위반

CLAUDE.md 의존성 방향 규칙 점검:

- **domain 레이어 프레임워크 import 금지**: FastAPI / SQLAlchemy / LangGraph / Celery import 있으면 위반 (pydantic은 허용).
- **domain 엔티티에 framework 이름 누설**: `celery_task_id` 같은 필드명 — import 아니어도 이름 종속. 추상 이름 권고.
- **application 레이어가 구체 Adapter 직접 import 금지**: Port ABC만 참조. 매직 라우팅 키 누설도 위반.
- **Composition Root 캡슐화**: `container._execution_repo` 같은 private attr 직접 접근 금지.
- **modules → services 역방향 의존 금지** (docstring 예시까지). services만 modules 조립 가능 — 단방향.
- **Port 정의/구현 분리**: Port(ABC)는 소유 모듈 `domain/ports/`, 구현은 `storage/repositories/` 또는 자체 `adapters/`.

> frontend / CI-YAML 등 레이어 무관 변경이면 "N/A — 위반 없음 ✓" 한 줄.

## Step 2. 축 2 — SSOT spec 기준 위반

- **docs/specs/REQ-XXX-*.md 동시 갱신**: use case 시그니처 / 엔티티 필드 / enum 변경 시 같은 PR에서 spec 갱신. 미갱신 = SSOT 깨짐 (HIGH).
- **common_schemas가 공유 타입 SSOT**: enums / workflow / agent / document / security / transport. 자체 재정의 시 위반. CHANGELOG + 버전 bump 확인.
- **CLAUDE.md 참조표 갱신**: 새 Port → "Port→Adapter 매핑" 표, 새 교차 import → "modules 간 허용 import" 표 행 추가됐는지.
- **PR 제목/scope ↔ 실제 변경 일치**: `fix:`인데 모듈 신규 추가면 scope mismatch (HIGH).
- **같은 이름 클래스 중복 정의**: drift 위험 → 이름 분리 권고.
- **매직 문자열 단일 정의**: 동일 상수(workspace 이름, task name 등)가 여러 곳 하드코딩 복붙되면 drift 위험.

## Step 3. 축 3 — 크로스 모듈 / 미래 안전성

- **race condition**: `find_by_id → None → create` 사이 동시 요청 → UNIQUE 위반. ON CONFLICT 확인.
- **트랜잭션 경계**: 여러 repo write가 별도 transaction이면 partial state. UoW 권고.
- **매직 문자열 중복 정의**: 생산자/소비자 양쪽 박힌 task name 등 — 단일 정의 + import.
- **환경변수/secret 누락**: Cloud Run env / Modal secret 런타임 키 누락 시 배포 즉시 crash. GCP Secret Manager 패턴 일관 적용 확인.
- **stale base / 머지 순서 의존성**: PR-A→PR-B 의존 시 순서 명시.
- **보안**: `debug=True` stacktrace 노출, OAuth state CSRF 미검증, secret 평문 노출, OpenAPI 공개 정책.
- **false healthy / silent fail**: `/health`가 broker 연결 미확인, `except: pass` 에러 삼킴, 컨트롤드 입력 false-fail 등.

---

## Step 4. 산출물 형식 (필수 — self-check)

리뷰 본문은 **반드시** 아래 구조를 모두 포함한다. 하나라도 빠지면 형식 위반.

```
## 3축 점검 결과
(범위 1줄: 파일/라인 규모 + 작성자)

### 축 1 — Clean Architecture
- 지적 또는 "위반 없음 ✓"

### 축 2 — SSOT spec
- 지적 또는 "N/A / 위반 없음 ✓"

### 축 3 — 크로스 모듈 / 미래 안전성
- 지적 또는 "위반 없음 ✓"

### 잘된 부분
- spec 동시 갱신 / ADR / graceful degradation 등 — 비판만 하지 않음

### 우선순위 요약
| 순위 | 항목 | 등급 | 영향 |

**머지 차단**: (차단 사유 유무 한 줄 판정)
```

- 각 지적에 **🔴 HIGH / 🟡 MEDIUM / 🟢 LOW** 등급 + `파일:라인` 인용 + 권고를 붙인다.
- 빈 축도 섹션을 생략하지 않는다.

## Step 5. 게시 (publish — 사전 확인 필수)

1. 위 본문을 **채팅에 먼저 제시**한다.
2. 사용자가 **"게시해"** 등으로 확인하면 게시한다. (publish 액션 — 무단 게시 금지)
3. 게시 명령은 `gh pr review <N> --comment --body-file <file>` 기본. `--request-changes`는 사용자가 명시할 때만.
   - 본문에 ``` `$(...)` ``` / 백틱이 있으면 shell이 평가하므로 **반드시 파일로 작성 후 `--body-file`** 사용 (`--body "..."` 인라인 금지).
   - 같은 PR 재리뷰로 직전 코멘트를 갈아끼울 땐 `gh pr comment <N> --edit-last --body-file <file>`.
4. 인자에 PR이 여러 개면 각각 독립 리뷰 + 독립 게시.

> 머지 클릭은 사용자(황대원) 권한 — Claude는 절대 머지하지 않는다. 본인 작성 PR도 동일.
