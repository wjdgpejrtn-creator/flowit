import { apiJson } from '@/lib/apiClient';
import type { NodeConfig } from '@common/generated';

export async function getCatalog(mvpOnly = false): Promise<NodeConfig[]> {
  return apiJson<NodeConfig[]>(`/api/v1/nodes/catalog?mvp_only=${mvpOnly}`);
}
