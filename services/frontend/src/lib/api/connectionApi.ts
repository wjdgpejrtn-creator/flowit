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
