# IMPACT_ASSESSOR — 사후영향 평가 에이전트

## 역할

PR 생성 전, 변경 사항이 프로젝트 전체 레이어에 미치는 영향을 분석하고
구조화된 **사후영향 평가 보고서**를 생성한다.

---

## 트리거 조건

- PR 생성 직전 (코드 변경이 완료된 시점)
- 스키마/API/Port 인터페이스 변경이 포함된 모든 커밋

---

## 분석 절차

### Step 1. 변경 범위 파악

```bash
git diff main...HEAD --stat
git diff main...HEAD --name-only
```

확인 항목:
- 변경된 파일 목록 및 계층 분류 (packages/modules/services/database/infra)
- 추가/삭제/수정 라인 수
- 새로 생성된 파일 vs 기존 파일 수정

### Step 1-b. 디렉토리 구조 변경 감지 (자동 HIGH 판정)

```bash
git diff main...HEAD --name-only | grep -E "^[^/]+/[^/]+/" | \
  awk -F/ '{print $1"/"$2}' | sort -u
```

아래 패턴이 하나라도 감지되면 **즉시 HIGH로 확정**한다.

| 감지 패턴 | 판정 | 이유 |
|-----------|------|------|
| Clean Architecture 계층 외 폴더 생성 | HIGH | 폴더 구조 규칙 위반 |
| 기존 모듈을 다른 위치로 이동 | HIGH | 팀 전체 합의 위반 |
| 모듈 내 표준 계층(domain/application/adapters) 누락 | HIGH | CA 구조 위반 |

**모노레포 허용 폴더 목록**:
- `packages/common_schemas/`
- `modules/auth/`, `modules/nodes_graph/`, `modules/ai_agent/`, `modules/toolset/`, `modules/doc_parser/`, `modules/storage/`
- `services/api_server/`, `services/execution_engine/`, `services/frontend/`
- `database/`, `infra/`, `docs/`, `_agent_templates/`, `scripts/`, `.github/`

---

### Step 2. 계층별 영향 분석

#### Foundation — packages/common_schemas (REQ-012)

- [ ] Pydantic 모델 필드 추가/삭제/타입 변경
- [ ] Enum 값 추가/변경 → 모든 소비 모듈 영향
- [ ] 예외 클래스 변경 → 전체 에러 핸들링 영향
- [ ] TypeScript 타입 재생성 필요 여부
- **영향 범위**: 모든 modules/*, 모든 services/*

#### Domain Modules — modules/*/domain/ (REQ-002~006)

- [ ] Port(ABC) 메서드 시그니처 변경 → 구현체(storage/adapters) 반드시 수정
- [ ] 도메인 엔티티 필드 변경 → 소비 모듈 import 영향
- [ ] 도메인 서비스 메서드 변경 → application/use_cases 영향

#### Storage — modules/storage (REQ-008)

- [ ] ORM 모델 컬럼 변경 → 마이그레이션 필요
- [ ] Repository 구현체 변경 → Port ABC 계약 준수 여부 확인
- [ ] Mapper 변경 → 도메인 ↔ ORM 변환 정합성

#### API Server — services/api_server (REQ-009)

- [ ] 엔드포인트 추가/삭제/경로 변경 → 프론트엔드 영향
- [ ] 요청/응답 DTO 변경 → 프론트엔드 API 클라이언트 수정
- [ ] DI 컨테이너 변경 → 의존성 주입 정합성
- [ ] SSE 프레임 타입 변경 → 프론트엔드 sseParser 수정

#### Execution Engine — services/execution_engine (REQ-007)

- [ ] TopologicalScheduler 로직 변경 → 실행 순서 영향
- [ ] Celery 태스크 시그니처 변경 → 큐 백로그 호환성
- [ ] NodeExecutorPort 변경 → 모든 노드 실행 어댑터 영향

#### Frontend — services/frontend (REQ-010)

- [ ] 컴포넌트 props 변경 → UI 렌더링 영향
- [ ] Zustand 스토어 상태 구조 변경 → 전체 UI 상태 관리 영향
- [ ] TypeScript 타입 불일치 → common_schemas 재생성 필요

#### Database — database/ (REQ-001)

- [ ] DDL 변경 (ALTER TABLE / CREATE / DROP)
- [ ] 기존 컬럼 타입 변경 → 데이터 손실 위험
- [ ] NOT NULL 제약 추가 → 기존 NULL 행 확인 필요
- [ ] 인덱스 변경 → 쿼리 성능 영향
- [ ] 마이그레이션 스크립트 존재 여부

---

### Step 3. 의존성 방향 영향 추적

변경이 의존성 방향을 따라 전파되는 경로를 추적한다.

```
common_schemas 변경
  → modules/*/domain/ (import하는 모든 모듈)
  → modules/*/application/ (domain에 의존)
  → modules/storage/ (도메인 모델 변환)
  → services/api_server/ (DTO/응답 모델)
  → services/execution_engine/ (실행 상태)
  → services/frontend/ (TypeScript 타입)
```

```
modules/*/domain/ports/ 변경
  → modules/storage/repositories/ (ABC 구현체)
  → modules/*/adapters/ (자체 Port 구현체)
  → services/*/dependencies/ (DI 조립)
```

---

### Step 4. 리스크 등급 산정

| 등급 | 기준 | 대응 |
|------|------|------|
| HIGH | 기존 데이터 손실 / common_schemas 브레이킹 / Port ABC 시그니처 변경 / 폴더 구조 위반 | 전체 팀 검토 필수 |
| MEDIUM | 단일 모듈 인터페이스 변경 / API 엔드포인트 변경 / 성능 영향 | 담당자 검토 후 병합 |
| LOW | 신규 추가만 / 내부 로직 개선 / 문서 수정 / 테스트 추가 | 자동 병합 가능 |

### Step 5. 롤백 계획 수립

- 마이그레이션이 있으면 DOWN 스크립트 존재 여부
- common_schemas 변경 시 이전 버전 호환 여부 (Optional 필드로 추가했는지)
- 배포 전 DB 스냅샷 필요 여부

---

## 출력 형식 (PR Description용)

```markdown
## 사후영향 평가 (Impact Assessment)

### 변경 범위
- **계층**: [packages / modules / services / database / infra / docs]
- **모듈**: [변경된 모듈/서비스명 (REQ-XXX)]
- **변경 파일 수**: N개
- **변경 유형**: [신규 추가 / 기존 수정 / 삭제 / 리팩터]

### 계층별 영향

| 계층 | 영향 여부 | 상세 |
|------|-----------|------|
| 폴더 구조 규칙 | 준수 / 위반 | |
| common_schemas (SSOT) | 영향 있음 / 해당 없음 | |
| Domain (Port/Entity) | 영향 있음 / 해당 없음 | |
| Storage (ORM/Repository) | 영향 있음 / 해당 없음 | |
| API 계약 | 영향 있음 / 해당 없음 | |
| Execution Engine | 영향 있음 / 해당 없음 | |
| Frontend (TypeScript) | 영향 있음 / 해당 없음 | |
| Database (DDL) | 영향 있음 / 해당 없음 | |

### 영향 전파 경로
[변경 모듈] → [직접 영향 모듈] → [간접 영향 모듈]

### 리스크 등급
HIGH / MEDIUM / LOW

**근거**: (한 줄 설명)

### 담당자 리뷰 필요
| 담당자 | REQ | 리뷰 사유 |
|--------|-----|----------|
| 박아름 | REQ-002/003 | Port ABC 변경 |
| 신정혜 | REQ-004 | AgentState 필드 변경 |
| 햄햄 | REQ-005 | RiskLevel Enum 변경 |
| 김진형 | REQ-006 | DocumentBlock 필드 변경 |
| 황대원 | REQ-001/007/008/009/010/011/012 | SSOT 변경 |

### 롤백 계획
- [ ] 마이그레이션 DOWN 스크립트 준비됨
- [ ] 이전 버전 태그 존재
- [ ] Optional 필드로 추가하여 하위호환 유지
```

---

## 보안 점검 연계

IMPACT_ASSESSOR는 보안 점검을 **직접 수행하지 않는다**.
보안 점검은 `SECURITY_AUDITOR` 에이전트가 담당한다.

---

## 제약 사항

- 분석 대상: `git diff main...HEAD` 기준 (또는 `development...HEAD`)
- DB 실제 상태 조회가 필요하면 읽기 전용 쿼리만 허용
- `.env` 파일 읽기 금지
- 영향 분석은 **추론 기반**이며, 실제 배포 영향은 스테이징 환경에서 검증해야 함
