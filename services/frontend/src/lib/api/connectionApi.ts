import { apiJson } from '@/lib/apiClient';

// GET /api/v1/connections 응답 (ADR-0027, #420 계약 잠김)
// service: 'google' | 'slack' | 'erp' / display: 이메일·workspace명(미확보 시 null)
// status: 'connected' | 'expired'
export interface ConnectionResponse {
  service: string;
  display: string | null;
  connected: boolean;
  status: string;
}

export async function getConnections(): Promise<ConnectionResponse[]> {
  return apiJson<ConnectionResponse[]>('/api/v1/connections');
}
