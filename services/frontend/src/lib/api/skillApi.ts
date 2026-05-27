import { apiFetch, apiJson } from '@/lib/apiClient';

export type SkillLifecycleState = 'draft' | 'review' | 'approved' | 'published';

export interface PersonalSkill {
  skill_id: string;
  owner_user_id: string;
  name: string;
  description: string;
  node_definition_id: string | null;
  lifecycle_state: SkillLifecycleState;
  skill_document_uri: string | null;
  workflow_id: string | null;
  tags: string[];
  version: string;
  promoted_to_team_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface UpdatePersonalSkillRequest {
  name?: string;
  description?: string;
  tags?: string[];
}

export async function listPersonalSkills(
  lifecycleState?: SkillLifecycleState,
  limit = 50,
  offset = 0,
): Promise<PersonalSkill[]> {
  const params = new URLSearchParams();
  if (lifecycleState) params.set('lifecycle_state', lifecycleState);
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  return apiJson<PersonalSkill[]>(`/api/v1/skills/personal?${params}`);
}

export async function getPersonalSkill(skillId: string): Promise<PersonalSkill> {
  return apiJson<PersonalSkill>(`/api/v1/skills/personal/${skillId}`);
}

export async function updatePersonalSkill(
  skillId: string,
  data: UpdatePersonalSkillRequest,
): Promise<PersonalSkill> {
  return apiJson<PersonalSkill>(`/api/v1/skills/personal/${skillId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deletePersonalSkill(skillId: string): Promise<void> {
  const res = await apiFetch(`/api/v1/skills/personal/${skillId}`, { method: 'DELETE' });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
}
