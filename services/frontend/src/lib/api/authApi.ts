import type { PermissionSource } from '@common/generated';
import { apiJson } from '@/lib/apiClient';

export type { PermissionSource };

export interface AuthorizeResponse {
  authorization_url: string;
  state: string;
}

export async function getAuthorizeUrl(): Promise<AuthorizeResponse> {
  return apiJson<AuthorizeResponse>('/api/v1/auth/authorize');
}

export async function me(): Promise<PermissionSource> {
  return apiJson<PermissionSource>('/api/v1/auth/me');
}
