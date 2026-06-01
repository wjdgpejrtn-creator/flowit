import { apiFetch, apiJson } from '@/lib/apiClient';

export type SkillLifecycleState = 'draft' | 'review' | 'approved' | 'published' | 'archived';

export interface PersonalSkill {
  skill_id: string;
  owner_user_id: string;
  name: string;
  description: string;
  node_definition_id: string | null;
  lifecycle_state: SkillLifecycleState;
  skill_document_uri: string | null;
  workflow_id: string | null;
  source_document_id: string | null;
  tags: string[];
  version: string;
  promoted_to_team_id: string | null;
  created_at: string;
  updated_at: string;
}

export type MarketplaceScope = 'team' | 'company';

// 마켓플레이스 Team/Company 탭 browse 응답 (백엔드 MarketplaceSkillResponse 대응).
// 검색어 없는 게시 스킬 목록 — SearchSkillsUseCase(embedding 유사도)와 별개 경로.
export interface MarketplaceSkill {
  skill_id: string;
  scope: MarketplaceScope;
  name: string;
  description: string;
  node_definition_id: string | null;
  lifecycle_state: SkillLifecycleState;
  tags: string[];
  version: string;
  created_at: string;
  updated_at: string;
}

// 스킬 지침서(SKILL.md) 본문 — 상세 페이지가 메타 조회 후 lazy-load (백엔드
// MarketplaceSkillDocumentResponse 대응). instructions = markdown 본문.
export interface MarketplaceSkillDocument {
  skill_id: string;
  name: string;
  description: string;
  instructions: string;
}

export interface CreatePersonalSkillRequest {
  name: string;
  description: string;
  instructions?: string;
  tags?: string[];
  // 기반 문서 association (REQ-010 문서→빌더 핸드오프). 백엔드 source_document_id 와이어업
  // 완료(POST /skills/personal). 직접 진입 시 생략.
  source_document_id?: string;
}

export interface UpdatePersonalSkillRequest {
  name?: string;
  description?: string;
  tags?: string[];
}

export async function createPersonalSkill(
  data: CreatePersonalSkillRequest,
): Promise<PersonalSkill> {
  return apiJson<PersonalSkill>('/api/v1/skills/personal', {
    method: 'POST',
    body: JSON.stringify(data),
  });
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

export async function listMarketplaceSkills(
  scope: MarketplaceScope,
  limit = 50,
  offset = 0,
): Promise<MarketplaceSkill[]> {
  const params = new URLSearchParams();
  params.set('scope', scope);
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  return apiJson<MarketplaceSkill[]>(`/api/v1/skills/marketplace?${params}`);
}

export async function getMarketplaceSkill(
  scope: MarketplaceScope,
  skillId: string,
): Promise<MarketplaceSkill> {
  const params = new URLSearchParams({ scope });
  return apiJson<MarketplaceSkill>(`/api/v1/skills/marketplace/${skillId}?${params}`);
}

export async function getMarketplaceSkillDocument(
  scope: MarketplaceScope,
  skillId: string,
): Promise<MarketplaceSkillDocument> {
  const params = new URLSearchParams({ scope });
  return apiJson<MarketplaceSkillDocument>(
    `/api/v1/skills/marketplace/${skillId}/document?${params}`,
  );
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

// ── 문서→스킬 자동 추출 (REQ-010/013, 스킬빌더 위저드 1단계) ────────────────────

// extract_draft 결과 1건 — SOP에서 추출된 SkillNode 초안. instructions가 전문 SKILL.md 본문.
export interface ExtractedSkillDraft {
  node_type: string;
  name: string;
  description: string;
  instructions: string;
}

// SOP 문서에서 스킬 초안을 추출하는 SSE 스트림 (POST /api/v1/skills/extract).
// onFrame으로 raw frame을 넘긴다 — 호출측이 frame_type으로 분기(agent_node/result/error).
// 저장은 하지 않는다(검토용) — 확정은 createPersonalSkill로 수행.
export async function streamExtractSkillFromDocument(
  sourceDocumentId: string,
  onFrame: (frame: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await apiFetch('/api/v1/skills/extract', {
    method: 'POST',
    body: JSON.stringify({ source_document_id: sourceDocumentId }),
    signal,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';

      for (const part of parts) {
        for (const line of part.split('\n')) {
          if (line.startsWith('data: ')) {
            try {
              onFrame(JSON.parse(line.slice(6)) as Record<string, unknown>);
            } catch { /* skip malformed */ }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
