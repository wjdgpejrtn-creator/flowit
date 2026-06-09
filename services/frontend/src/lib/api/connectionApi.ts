import { apiJson } from '@/lib/apiClient';
import type { ConnectionStatus } from '@common/generated';

// GET /api/v1/connections 응답 (ADR-0027, #420 계약 잠김)
// 타입은 common_schemas SSOT(ConnectionStatus)를 generated에서 그대로 사용:
//   service: 'google' | 'slack' | 'erp' / display: 이메일·workspace명(미확보 시 null)
//   connected: bool / status: 'connected' | 'expired'
export type { ConnectionStatus };

export async function getConnections(): Promise<ConnectionStatus[]> {
  return apiJson<ConnectionStatus[]>('/api/v1/connections');
}

// GET /api/v1/connections/{service}/authorize → 동의 화면 URL 발급(ADR-0027).
// 받은 authorization_url로 전체 페이지를 넘겨 OAuth 동의를 띄운다. callback이 끝나면
// 백엔드가 /settings?connected={service} 또는 ?error=connect_failed 로 되돌려보낸다.
interface AuthorizeConnectionResponse {
  authorization_url: string;
  state: string;
}

export async function startConnection(service: string): Promise<void> {
  const { authorization_url } = await apiJson<AuthorizeConnectionResponse>(
    `/api/v1/connections/${service}/authorize`,
  );
  window.location.href = authorization_url;
}

// DELETE /api/v1/connections/{service} → 연결 해제(ADR-0027).
export async function revokeConnection(service: string): Promise<void> {
  await apiJson(`/api/v1/connections/${service}`, { method: 'DELETE' });
}
