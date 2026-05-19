# REQ-011 Infra — 구현 명세

## common_schemas에서 import할 클래스

| 클래스 | 소스 모듈 | 용도 |
|--------|-----------|------|
| `ExecutionStatus` | enums | 헬스체크/모니터링 상태 매핑 |
| `ErrorCode` | enums | 알럿 분류 |

## 이 모듈에서 구현/관리할 리소스

### Terraform (infra/terraform/)

| 리소스 | 설명 |
|--------|------|
| `Cloud Run (api_server)` | REQ-009 API 서버 배포 |
| `Cloud Run (execution_engine)` | REQ-007 실행 엔진 배포 |
| `Cloud SQL (PostgreSQL 15)` | REQ-001 Database + pgvector |
| `Cloud Storage` | REQ-008 파일 저장소 |
| `Redis (Memorystore)` | Celery broker + 세션 캐시 |
| `Artifact Registry` | Docker 이미지 저장 |
| `Secret Manager` | 환경변수/자격증명 관리 |
| `Cloud Armor` | WAF/DDoS 방어 |
| `Workload Identity Federation` | CI/CD 인증 (키 없이) |

### CI/CD (GitHub Actions)

| Workflow | 트리거 | 역할 |
|----------|--------|------|
| `deploy-prod.yml` | push to release | Cloud Run 프로덕션 배포 |
| `codegen-drift.yml` | PR/push (common_schemas 변경 시) | TS codegen 정합성 검증 |
| `secret-scan.yml` | push | 시크릿 유출 탐지 |
| (추가 예정) `test.yml` | PR | pytest + ruff + tsc |

### 모니터링/관측성

| 컴포넌트 | 도구 | 설명 |
|----------|------|------|
| 메트릭 | Cloud Monitoring | CPU, 메모리, 요청 지연 |
| 로그 | Cloud Logging | 구조화 로그 (JSON) |
| 트레이싱 | Cloud Trace | 요청 경로 추적 |
| 알럿 | Cloud Monitoring Alerting | SLO 위반 시 Slack 알림 |

### 네트워크/보안

| 항목 | 설정 |
|------|------|
| VPC | Serverless VPC Connector (Cloud Run ↔ Cloud SQL) |
| IAM | 서비스별 SA, 최소 권한 원칙 |
| SSL | Google-managed 인증서 (Cloud Run 기본) |
| CORS | API Server에서 프론트엔드 도메인만 허용 |

## 의존성 관계

```
upstream:  없음 (인프라 최하위 레이어)
downstream: 모든 모듈 (배포/실행 환경 제공)
external: GCP, GitHub Actions, Modal (REQ-004 LLM inference)
```

## 환경 분리

| 환경 | 트리거 | 인프라 |
|------|--------|--------|
| dev | 로컬 docker-compose | SQLite/Redis 로컬 |
| staging | development 브랜치 merge | GCP dev 프로젝트 |
| production | release 브랜치 push | GCP prod 프로젝트 |
