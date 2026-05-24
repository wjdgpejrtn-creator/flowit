# 2단계 apply 보조 — 프론트 배포(stage 1) 후 frontend_url을 확인해
# var.frontend_url + google-redirect-uri secret(stage 2)에 반영한다.

output "api_server_url" {
  description = "api_server Cloud Run URL"
  value       = try(module.api_server[0].service_url, "")
}

output "frontend_url" {
  description = "frontend Cloud Run URL — 단일 출처 진입점. var.frontend_url + google-redirect-uri secret에 반영"
  value       = try(module.frontend[0].service_url, "")
}

output "api_server_runtime_sa" {
  description = "api_server 전용 Cloud Run runtime SA email (PR2 단계에서 tfvars `api_server_service_account`와 Cloud SQL IAM user 등록에 사용)"
  value       = try(google_service_account.api_server[0].email, "")
}
