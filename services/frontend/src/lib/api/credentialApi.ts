import { apiJson } from '@/lib/apiClient';

// 관리자 자격증명 감사 1행 (백엔드 ConnectionAuditEntry 대응) — 전사 OAuth connection + 소유자.
// 토큰은 포함되지 않는다(감사 화면 불필요·민감). 사용량/만료 지표는 현재 데이터 모델에 소스가
// 없어 제외(실 필드만). owner_department는 표시용 라벨이라 null일 수 있다.
export interface CredentialAuditEntry {
  oauth_id: string;
  user_id: string;
  owner_email: string;
  owner_name: string;
  owner_department: string | null;
  service: 'google' | 'slack';
  account_id: string | null;
  display_name: string | null;
  scopes: string[];
  is_active: boolean;
  connected_at: string;
  last_refreshed_at: string | null;
}

// 관리자 자격증명 감사 — 전사 OAuth connection 목록 (Admin only — 비-Admin은 403).
// 연결일(connected_at) 최신순. limit/offset 페이지네이션.
export async function listCredentialAudit(
  limit = 200,
  offset = 0,
): Promise<CredentialAuditEntry[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiJson<CredentialAuditEntry[]>(`/api/v1/auth/admin/credentials?${params}`);
}
