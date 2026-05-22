import { apiJson } from '@/lib/apiClient';

export interface AuthorizeResponse {
  authorization_url: string;
  state: string;
}

export interface UserInfo {
  user_id: string;
  email: string;
  role: string;
  dept: string | null;
  team_id: string | null;
}

export async function getAuthorizeUrl(): Promise<AuthorizeResponse> {
  return apiJson<AuthorizeResponse>('/api/v1/auth/authorize');
}

export async function me(): Promise<UserInfo> {
  return apiJson<UserInfo>('/api/v1/auth/me');
}
