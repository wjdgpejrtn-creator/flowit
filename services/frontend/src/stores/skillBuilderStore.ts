import { create } from 'zustand';
import { showToast } from '@/stores/toastStore';
import {
  createPersonalSkill,
  selfPublishPersonalSkill,
  getPersonalSkill,
  streamExtractSkill,
  extractSkillDetail,
} from '@/lib/api/skillApi';
import type {
  PersonalSkill,
  SkillMeta,
  ExtractMaterial,
  NodeSpecStagingInput,
} from '@/lib/api/skillApi';

/**
 * 스킬빌더 위저드 공유 상태(zustand).
 *
 * 이전에는 `app/skills/builder/page.tsx`의 page-local useState였으나, 위저드를
 * (a) 독립 빌더 페이지, (b) 문서 탭 서브뷰, (c) AI 채팅의 좌측 카드 + 우측 캔버스
 * 세 진입점에서 공유하기 위해 store로 승격했다. 채팅에서는 위저드의 *선택*(재료/초안)을
 * 좌측 인라인 카드가, *편집*(폼/지침서/게시)을 우측 캔버스가 담당하므로 — 멀리 떨어진
 * 두 서브트리가 같은 진행 상태를 봐야 한다(page-local로는 불가).
 *
 * 비즈니스 흐름은 기존 page.tsx와 동일하다(#353 2단계 메타/디테일, #290 staging,
 * 빈 지침서 방지 가드 포함). 동작 회귀는 SkillBuilderPage.test.tsx가 지킨다.
 */

// 위저드 추출 재료 — 내 문서 또는 default 템플릿. label은 build 단계 상단 표시용.
export type Material =
  | { kind: 'document'; id: string; label: string }
  | { kind: 'template'; code: string; label: string };

export function toExtractBody(m: Material): ExtractMaterial {
  return m.kind === 'document' ? { source_document_id: m.id } : { template_code: m.code };
}

const STEP_LABELS: Record<string, string> = {
  'skills_builder.sop.parse_document': '문서 파싱 중…',
  'skills_builder.sop.llm_extract': 'AI가 스킬을 추출 중…',
};

interface SkillBuilderState {
  // 위저드 단계 — 'choose'(재료 선택) → 'build'(추출·검토·생성).
  phase: 'choose' | 'build';
  // 'choose' 내 분기 — 'ask'(문서 有無) → 'document' | 'template'.
  branch: 'ask' | 'document' | 'template';
  material: Material | null;

  // 폼 상태
  name: string;
  description: string;
  instructions: string;
  tagsInput: string;
  loading: boolean;
  error: string | null;
  created: PersonalSkill | null;

  // 마켓 '수정' → 편집 모드(위저드 건너뛰고 폼 prefill).
  isEdit: boolean;
  editLabel: string;

  // 추출(위저드 1단계) 상태
  extracting: boolean;
  extractStep: string | null;
  extractError: string | null;
  extractedSkills: SkillMeta[];
  selectedDraftIdx: number | null;
  detailLoadingIdx: number | null;
  selectedStaging: NodeSpecStagingInput | undefined;

  // 진행 중 추출 SSE의 AbortController(비영속 ref성 필드).
  _abort: AbortController | null;

  // 단순 setter
  setBranch: (b: SkillBuilderState['branch']) => void;
  setName: (v: string) => void;
  setDescription: (v: string) => void;
  setInstructions: (v: string) => void;
  setTagsInput: (v: string) => void;

  // 액션
  runExtract: (m: Material) => Promise<void>;
  selectDraft: (meta: SkillMeta, idx: number, m: Material | null) => Promise<void>;
  startBuild: (m: Material) => void;
  handleCreate: (publish: boolean) => Promise<void>;
  resetToChoose: () => void;
  initEdit: (args: { name: string; description: string; tags: string }) => void;
  reset: () => void;
}

const INITIAL = {
  phase: 'choose' as const,
  branch: 'ask' as const,
  material: null,
  name: '',
  description: '',
  instructions: '',
  tagsInput: '',
  loading: false,
  error: null,
  created: null,
  isEdit: false,
  editLabel: '',
  extracting: false,
  extractStep: null,
  extractError: null,
  extractedSkills: [],
  selectedDraftIdx: null,
  detailLoadingIdx: null,
  selectedStaging: undefined,
  _abort: null,
};

export const useSkillBuilderStore = create<SkillBuilderState>()((set, get) => ({
  ...INITIAL,

  setBranch: (branch) => set({ branch }),
  setName: (name) => set({ name }),
  setDescription: (description) => set({ description }),
  setInstructions: (instructions) => set({ instructions }),
  setTagsInput: (tagsInput) => set({ tagsInput }),

  // 추출 메타 1건 선택 → 폼에 채운다(검토·수정용). 메타(name/description)는 즉시 채우고,
  // instructions/staging은 2차 detail 호출로 채운다(#353 metadata/detail 2단계). 재료(m)는
  // stale closure 회피를 위해 인자로 직접 받는다.
  selectDraft: async (meta, idx, m) => {
    set({
      selectedDraftIdx: idx,
      name: meta.name,
      description: meta.description,
      // detail이 올 때까지 이전 선택의 잔재를 비운다(혼동 방지).
      instructions: '',
      selectedStaging: undefined,
    });
    if (!m) return;
    set({ detailLoadingIdx: idx, extractError: null });
    try {
      const detail = await extractSkillDetail(toExtractBody(m), meta);
      set({ instructions: detail.instructions, selectedStaging: detail.staging });
    } catch (err) {
      set({
        extractError: err instanceof Error ? `상세 추출 실패: ${err.message}` : '상세 추출 실패',
      });
    } finally {
      set({ detailLoadingIdx: null });
    }
  },

  // 위저드 1단계 — 재료(문서/템플릿)에서 SkillNode 초안 추출(SSE). 결과를 목록으로 보여주고
  // 사용자가 1건 선택하면 폼에 prefill(단일이면 자동). 저장은 handleCreate에서 수행.
  runExtract: async (m) => {
    get()._abort?.abort();
    const controller = new AbortController();
    set({
      _abort: controller,
      extracting: true,
      extractError: null,
      extractStep: null,
      extractedSkills: [],
      selectedDraftIdx: null,
      detailLoadingIdx: null,
    });

    try {
      await streamExtractSkill(
        toExtractBody(m),
        (frame) => {
          switch (frame.frame_type) {
            case 'agent_node': {
              const node = frame.agent_node_name as string;
              set({ extractStep: STEP_LABELS[node] ?? '처리 중…' });
              break;
            }
            case 'result': {
              // 백엔드는 metadata 단계에서 payload.skill_metas(5필드 메타 목록)를 보낸다(#353).
              const payload = frame.payload as { skill_metas?: SkillMeta[] } | undefined;
              const metas = payload?.skill_metas ?? [];
              set({ extractedSkills: metas });
              // 단건이면 자동 선택 → 곧장 detail까지 채운다(재료는 인자 m으로 전달, stale 회피).
              if (metas.length === 1) void get().selectDraft(metas[0], 0, m);
              break;
            }
            case 'error':
              set({ extractError: (frame.message as string) ?? '추출 중 오류가 발생했습니다.' });
              break;
          }
        },
        controller.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      set({ extractError: err instanceof Error ? err.message : '추출 요청 실패' });
    } finally {
      set({ extracting: false, extractStep: null });
    }
  },

  // build 단계 진입 + 추출 시작. 재료를 인자로 직접 받아 stale closure 회피.
  startBuild: (m) => {
    set({
      material: m,
      phase: 'build',
      name: '',
      description: '',
      instructions: '',
      extractedSkills: [],
      selectedDraftIdx: null,
      detailLoadingIdx: null,
      selectedStaging: undefined,
    });
    void get().runExtract(m);
  },

  // 생성. publish=true면 personal self-publish 체인(owner 권한)으로 즉시 PUBLISHED.
  // publish=false면 DRAFT로만 저장. staging(추출 노드 스펙)을 함께 보내 publish 시
  // NodeDefinition I/O를 채운다(#290).
  handleCreate: async (publish) => {
    const { name, description, instructions, tagsInput, material, selectedDraftIdx, selectedStaging, isEdit } = get();
    if (!name.trim() || !description.trim()) return;
    // 방어선 — 버튼 disabled를 우회한 제출(엔터 등)도 미완 detail 상태면 차단(빈 지침서 방지).
    if (selectedDraftIdx !== null && selectedStaging === undefined) return;
    const tags = tagsInput.split(',').map((t) => t.trim()).filter(Boolean);
    set({ loading: true, error: null });
    try {
      const draft = await createPersonalSkill({
        name: name.trim(),
        description: description.trim(),
        instructions: instructions.trim() || undefined,
        tags,
        // 템플릿 기반 생성은 source_document_id 없음(전역 seed). 문서 기반만 association.
        source_document_id: material?.kind === 'document' ? material.id : undefined,
        node_spec_staging: selectedStaging,
      });
      if (publish) {
        // self-publish 실패해도 DRAFT는 이미 생성됨 — 에러를 표면화하되 created(draft)는 보여준다.
        try {
          await selfPublishPersonalSkill(draft.skill_id);
          set({ created: await getPersonalSkill(draft.skill_id) });
          showToast('스킬을 게시했습니다. 워크플로우에서 바로 사용할 수 있어요.');
        } catch (pubErr) {
          set({ error: pubErr instanceof Error ? pubErr.message : '게시 처리 실패 — 초안은 저장됨' });
          try {
            set({ created: await getPersonalSkill(draft.skill_id) });
          } catch {
            set({ created: draft });
          }
        }
      } else {
        set({ created: draft });
        showToast(isEdit ? '변경 사항을 저장했습니다.' : `'${draft.name}' 스킬을 DRAFT로 등록했습니다.`);
      }
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '스킬 생성 실패' });
    } finally {
      set({ loading: false });
    }
  },

  resetToChoose: () => {
    get()._abort?.abort();
    set({
      phase: 'choose',
      branch: 'ask',
      material: null,
      extractedSkills: [],
      extractError: null,
      selectedDraftIdx: null,
      selectedStaging: undefined,
    });
  },

  initEdit: ({ name, description, tags }) => {
    set({ isEdit: true, editLabel: name, name, description, tagsInput: tags, phase: 'build' });
  },

  reset: () => {
    get()._abort?.abort();
    set({ ...INITIAL });
  },
}));
