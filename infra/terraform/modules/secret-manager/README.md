# secret-manager

GCP Secret Manager에 secret 객체를 생성하고, 지정한 IAM 멤버에게 `roles/secretmanager.secretAccessor`를 부여한다.

값은 Terraform이 관리하지 않는다 — secret 객체와 IAM만 관리. 값 push는 `gcloud secrets versions add` 또는 콘솔로 별도 수행.

## 사용 예

```hcl
module "agent_secrets" {
  source = "../../modules/secret-manager"

  project_id = var.project_id
  secret_names = [
    "llm-base-url",
    "embedding-base-url",
    "cloud-sql-instance",
  ]
  accessor_members = [
    "serviceAccount:cloudsql-iam-modal@${var.project_id}.iam.gserviceaccount.com",
    "user:dhwang0803@gmail.com",
  ]
}
```

## 값 push (별도 단계)

```bash
echo -n "https://<WORKSPACE>--llm-base.modal.run" \
  | gcloud secrets versions add llm-base-url --data-file=- --project=<GCP_PROJECT_ID>
```

## 회전

새 버전을 add. 이전 버전은 `disable` 또는 `destroy`. Modal app은 `versions/latest`를 pull하므로 코드 변경 불필요.
