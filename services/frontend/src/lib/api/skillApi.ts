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

// 노드 스펙 staging — 추출 초안의 실 스펙(백엔드 NodeSpecStaging VO 대응). publish 시 NodeDefinition
// 의 실제 입출력/위험도/연동이 된다. 미전달 시 백엔드가 placeholder(action/빈 스키마/LOW) 폴백.
export type SkillRiskLevel = 'Low' | 'Medium' | 'High' | 'Restricted';
export interface NodeSpecStagingInput {
  category: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  risk_level: SkillRiskLevel;
  required_connections?: string[];
  service_type?: string | null;
}

export interface CreatePersonalSkillRequest {
  name: string;
  description: string;
  instructions?: string;
  tags?: string[];
  // 기반 문서 association (REQ-010 문서→빌더 핸드오프). 백엔드 source_document_id 와이어업
  // 완료(POST /skills/personal). 직접 진입 시 생략.
  source_document_id?: string;
  // 추출 초안의 노드 스펙 — publish 시 워크플로우 노드 I/O가 된다(#290). 수동 폼은 생략.
  node_spec_staging?: NodeSpecStagingInput;
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

// ── 게시 lifecycle (DRAFT→REVIEW→APPROVED→PUBLISHED) ─────────────────────────
// personal scope는 owner가 3전이를 모두 수행 가능(RBAC: personal=owner). 위저드 self-publish용.
export type SkillScope = 'personal' | 'team' | 'company';

export async function submitSkill(skillId: string, scope: SkillScope = 'personal'): Promise<void> {
  await apiJson(`/api/v1/skills/${skillId}/submit`, {
    method: 'POST',
    body: JSON.stringify({ scope }),
  });
}

export async function approveSkill(
  skillId: string,
  scope: SkillScope = 'personal',
  approved = true,
): Promise<void> {
  await apiJson(`/api/v1/skills/${skillId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ scope, approved }),
  });
}

export async function publishSkill(skillId: string, scope: SkillScope = 'personal'): Promise<void> {
  await apiJson(`/api/v1/skills/${skillId}/publish`, {
    method: 'POST',
    body: JSON.stringify({ scope }),
  });
}

// personal self-publish — owner가 DRAFT를 한 번에 PUBLISHED로(검토 & 게시). 워크플로우에 즉시 노출.
// 단계별 실패를 구분해 던진다(어느 전이에서 멈췄는지 — 스킬은 이미 생성돼 있어 마켓플레이스에서 재개 가능).
export async function selfPublishPersonalSkill(skillId: string): Promise<void> {
  const steps: ReadonlyArray<readonly [string, () => Promise<void>]> = [
    ['리뷰 요청', () => submitSkill(skillId, 'personal')],
    ['승인', () => approveSkill(skillId, 'personal', true)],
    ['게시', () => publishSkill(skillId, 'personal')],
  ];
  for (const [label, run] of steps) {
    try {
      await run();
    } catch (err) {
      const reason = err instanceof Error ? err.message : String(err);
      throw new Error(`${label} 단계 실패: ${reason}`);
    }
  }
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

// ── default 템플릿(seed) — 문서 없는 사용자용 위저드 재료 (위저드 재설계 Phase 0/1) ──

export type SkillTemplateKind = 'industry' | 'functional';

// default 위저드 카드 1건 (백엔드 SkillTemplate 대응). code → extract의 template_code.
export interface SkillTemplate {
  code: string;
  name: string;
  description: string;
  kind: SkillTemplateKind;
}

// 사용 가능한 default 템플릿(업종 6 + 직무 5) 목록 — GET /api/v1/skills/templates.
export async function listSkillTemplates(): Promise<SkillTemplate[]> {
  return apiJson<SkillTemplate[]>('/api/v1/skills/templates');
}

// ── 문서/템플릿→스킬 자동 추출 (REQ-010/013, 스킬빌더 위저드 1단계) ──────────────

// extract_draft 결과 1건 — SOP에서 추출된 SkillNode 초안. instructions가 전문 SKILL.md 본문.
// staging은 노드 스펙(category/입출력/risk/연동) — 생성 시 그대로 실어 보내 publish 노드 I/O를 채운다.
export interface ExtractedSkillDraft {
  node_type: string;
  name: string;
  description: string;
  instructions: string;
  staging?: NodeSpecStagingInput;
}

// 추출 재료 — 내 문서(source_document_id) XOR default 템플릿(template_code). 백엔드 배타 검증.
export type ExtractMaterial =
  | { source_document_id: string }
  | { template_code: string };

// 문서 또는 default 템플릿에서 스킬 초안을 추출하는 SSE 스트림 (POST /api/v1/skills/extract).
// onFrame으로 raw frame을 넘긴다 — 호출측이 frame_type으로 분기(agent_node/result/error).
// 저장은 하지 않는다(검토용) — 확정은 createPersonalSkill로 수행.
export async function streamExtractSkill(
  material: ExtractMaterial,
  onFrame: (frame: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await apiFetch('/api/v1/skills/extract', {
    method: 'POST',
    body: JSON.stringify(material),
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
