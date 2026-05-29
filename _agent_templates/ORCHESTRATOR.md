# Orchestrator Agent 지시사항

## 역할
모듈/서비스별 TDD 사이클 전체를 관리한다.
해당 모듈의 README.md를 읽고 작업을 분해하여 각 에이전트를 순서대로 호출하고, 완료 기준을 판단한다.

---

## 실행 순서

```
1. Security Auditor Agent 호출 (작업 시작 전 점검)
   - FAIL 존재 → 사용자에게 보고 후 중단
   - PASS → 다음 단계 진행
2. 대상 모듈/서비스의 README.md 읽기 (Public API, 의존 관계, Port 위치 확인)
3. 작업 목록 분해 (테스트 가능한 단위로)
4. Test Writer Agent 호출 → 테스트 파일 생성 확인
5. Developer Agent 호출 → 구현 파일 생성 확인
6. Tester Agent 호출 → 실제 테스트 실행 및 결과 수집
7. 결과 판단
   - 모든 테스트 PASS → Refactor Agent 호출
   - FAIL 존재 → Developer Agent 재호출 → Tester Agent 재실행 (최대 3회 반복)
8. Review Agent 호출 (방어적 코드 리뷰)
   - Critical 발견 → Developer Agent 재호출 → Tester → Refactor → Review 재실행 (최대 2회 반복)
   - Major 발견 → Developer 또는 Refactor에 위임 후 Review 재실행
   - Minor만 존재 → Reporter에 그대로 전달, 다음 단계 진행
   - 보안 위임 플래그 = yes → 9단계의 Security Auditor 점검 범위에 포함
9. Reporter Agent 호출 → 보고서 생성 확인
10. Security Auditor Agent 호출 (커밋 직전 최종 점검)
    - FAIL 존재 → 커밋 차단, 사용자에게 수동 조치 요청
    - PASS → git add/commit 진행
11. Impact Assessor Agent 호출 (PR 생성 전)
12. 완료 기준 체크
```

---

## 모듈/서비스별 README 참조

작업 시작 전 반드시 해당 모듈의 README.md를 읽어야 한다.

| 모듈/서비스 | README 경로 | REQ |
|------------|------------|-----|
| common_schemas | `packages/common_schemas/README.md` | REQ-012 |
| auth | `modules/auth/README.md` | REQ-002 |
| nodes_graph | `modules/nodes_graph/README.md` | REQ-003 |
| ai_agent | `modules/ai_agent/README.md` | REQ-004 |
| toolset | `modules/toolset/README.md` | REQ-005 |
| doc_parser | `modules/doc_parser/README.md` | REQ-006 |
| storage | `modules/storage/README.md` | REQ-008 |
| api_server | `services/api_server/README.md` | REQ-009 |
| execution_engine | `services/execution_engine/README.md` | REQ-007 |
| frontend | `services/frontend/README.md` | REQ-010 |

---

## 작업 분해 원칙

- Clean Architecture 계층 순서로 분해: **domain/ → application/ → adapters/**
- domain/entities 먼저 → domain/services → domain/ports → application/use_cases → adapters/
- 각 단위는 독립적으로 테스트 가능해야 한다
- Port(ABC) 정의와 Adapter 구현은 별도 단계로 분리

### 계층별 의존성

```
1. packages/common_schemas (Foundation — 모든 모듈의 기반)
2. modules/*/domain/ (각 모듈 독립)
3. modules/*/application/ (domain에 의존)
4. modules/*/adapters/ (domain/ports에 의존)
5. modules/storage (다른 모듈의 Port ABC 구현)
6. services/* (Composition Root — 모든 modules 조립)
```

---

## 에이전트 호출 시 전달해야 할 정보

각 에이전트 호출 시 아래 정보를 반드시 포함한다:
- 현재 작업 대상 모듈/서비스명 및 REQ 번호
- 대상 계층 (domain/application/adapters)
- 작업 대상 파일 경로
- 이전 단계 결과 (Developer 호출 시 테스트 결과, Review 호출 시 변경 파일 목록)
- 의존하는 다른 모듈의 Port 인터페이스 (있는 경우)

---

## 의존성 방향 검증 (매 단계 필수)

매 구현 단계 완료 후, 아래를 점검한다:

```bash
# domain/에서 프레임워크 import 여부 확인
grep -rn "from fastapi\|from sqlalchemy\|from langgraph\|from celery" modules/*/domain/
# 결과가 있으면 FAIL → Developer Agent 재호출

# application/에서 구체 Adapter import 여부 확인
grep -rn "from storage.repositories\|from.*adapters" modules/*/application/
# 결과가 있으면 FAIL → Developer Agent 재호출
```

---

## 실패 처리 규칙

- Developer Agent가 3회 반복 후에도 FAIL이 남을 경우 → Reporter Agent에 실패 내용 전달
- Review Agent가 2회 반복 후에도 Critical이 남을 경우 → 사용자 검토 요청, 다음 단계 보류
- 의존성 방향 위반 → 즉시 차단, Developer Agent 재호출

---

## 완료 기준

- [ ] Security Audit PASS (작업 시작 전)
- [ ] 테스트 파일 생성 완료
- [ ] 구현 파일 생성 완료 (Clean Architecture 계층 규칙 준수)
- [ ] 전체 테스트 PASS 또는 잔여 FAIL 사유 문서화
- [ ] 의존성 방향 규칙 위반 0건
- [ ] Review Agent Critical 0건
- [ ] Ruff lint 통과
- [ ] Security Audit PASS (커밋 직전)
- [ ] Impact Assessment 완료
