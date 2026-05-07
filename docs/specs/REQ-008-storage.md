# REQ-008 Storage — 구현 명세

## common-schemas에서 import할 클래스

| 클래스 | 소스 모듈 | 용도 |
|--------|-----------|------|
| `FileMeta` | document | 업로드 파일 메타데이터 생성/검증 |
| `DocumentBlock` | document | 파싱 결과물 저장 시 타입 참조 |
| `PermissionSource` | security | 파일 접근 권한 검증 |
| `RiskLevel` | enums | 파일 보안 등급 분류 |

## 이 모듈에서 구현할 클래스

### Domain Layer

| 클래스 | 설명 |
|--------|------|
| `StorageObject` | 저장된 파일 엔티티 (object_id, bucket, key, size, content_type, metadata) |
| `UploadPolicy` | 업로드 정책 VO (max_size, allowed_types, virus_scan_required) |
| `StorageEvent` | 이벤트 VO (uploaded, downloaded, deleted, expired) |
| `RetentionPolicy` | 보존 정책 VO (ttl_days, archive_after_days) |

### Port (domain/ports/)

| Port | 메서드 |
|------|--------|
| `ObjectStoragePort` | upload(key, data, metadata)→url, download(key)→bytes, delete(key)→None, presign(key, ttl)→url |
| `VirusScanPort` | scan(data)→ScanResult |
| `StorageEventPort` | emit(event)→None |

### Application Layer

| UseCase | 설명 |
|---------|------|
| `UploadFileUseCase` | 정책 검증 → 바이러스 스캔 → GCS 업로드 → FileMeta 생성 |
| `DownloadFileUseCase` | 권한 검증 → presigned URL 또는 직접 다운로드 |
| `DeleteFileUseCase` | 소유자 검증 → 삭제 → 이벤트 발행 |
| `CleanupExpiredUseCase` | 보존 정책에 따른 만료 파일 정리 (cron) |

### Adapter Layer

| Adapter | 설명 |
|---------|------|
| `GCSAdapter` | Google Cloud Storage 클라이언트 구현 |
| `ClamAVAdapter` | 바이러스 스캔 (ClamAV daemon) |
| `LocalStorageAdapter` | 로컬 개발용 파일시스템 저장소 |

## 의존성 관계

```
upstream:  REQ-002 (PermissionSource 권한 검증), REQ-006 (파싱 대상 원본 파일)
downstream: REQ-006 (원본 파일 읽기), REQ-010 (파일 다운로드/미리보기)
infra: GCP Cloud Storage, ClamAV
```
