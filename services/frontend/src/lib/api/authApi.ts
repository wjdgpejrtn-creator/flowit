import type { PermissionSource } from '@common/generated';
import { apiJson } from '@/lib/apiClient';

export type { PermissionSource };

export interface MeResponse extends PermissionSource {
  name: string;
  email: string;
  // 표시용 부서 라벨(users.department 문자열). authz는 department_id(UUID)가 담당.
  // AppBar 배지에 사람이 읽는 부서명 출력용. 미설정 시 null.
  department: string | null;
}

export interface AuthorizeResponse {
  authorization_url: string;
  state: string;
}

export async function getAuthorizeUrl(): Promise<AuthorizeResponse> {
  return apiJson<AuthorizeResponse>('/api/v1/auth/authorize');
}

export async function me(): Promise<MeResponse> {
  return apiJson<MeResponse>('/api/v1/auth/me');
}
