output "host" {
  description = "Redis private IP"
  value       = google_redis_instance.redis.host
}

output "port" {
  description = "Redis port (default 6379)"
  value       = google_redis_instance.redis.port
}

output "auth_string" {
  description = "Redis AUTH password (sensitive, store in Secret Manager)"
  value       = google_redis_instance.redis.auth_string
  sensitive   = true
}

output "current_location_id" {
  description = "Currently active zone for the instance"
  value       = google_redis_instance.redis.current_location_id
}

output "redis_url" {
  description = "redis:// URL stub (without password) for application config"
  value       = "redis://${google_redis_instance.redis.host}:${google_redis_instance.redis.port}"
}
