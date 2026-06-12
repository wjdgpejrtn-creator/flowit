import type { AgentStep } from '@/stores/agentStore';

// 컨펌 게이트 파이프라인 단계 표시 — agent_node 프레임 ↔ 사용자 표시 단계 매핑/순서.
// page.tsx에서 분리(순수 로직 단위 테스트 가능).

// 컴포저 파이프라인 단계(비복합 흐름의 기본 표시 순서).
export const STEP_ORDER: AgentStep[] = [
  'security', 'intent', 'retriever', 'drafter', 'validator', 'qa_eval', 'promote',
];

// 단조증가 가드/인덱스 계산의 기준 순서. 복합(skill_then_compose) 흐름의 선두
// 단계 'skill'은 컴포저 파이프라인보다 **항상 앞**(index 0)이라, 스킬 빌드 홉
// 이후 시작되는 컴포저 파이프라인(security…) 단계가 역행하지 않는다.
const GUARD_ORDER: AgentStep[] = ['skill', ...STEP_ORDER];

export const TOOL_TO_STEP: Record<string, AgentStep> = {
  // 복합 흐름 1홉 — 스킬 빌드 (supervisor build_skill 마커 + skills_builder.* 릴레이는 prefix로 매핑)
  build_skill:       'skill',
  // supervisor 노드
  load_memory:       'security',
  analyze_intent:    'intent',
  // composer fixed DAG 노드
  compress:          'security',
  security:          'security',
  intent:            'intent',
  consultant:        'intent',
  slot_fill:         'intent',
  search_nodes:      'retriever',
  suggest_skill_select: 'retriever',  // 노드 검색 직후 커스텀 스킬 제안 — 같은 '노드 검색' 단계
  // two-shot 2차 resume 경로 — 진행 안내 메시지가 침묵 처리되므로 단계로 피드백을 준다.
  resume:            'retriever',      // GCS 상태(노드 검색 결과) 복원
  bind_skill:        'drafter',        // 선택 스킬 지침서 바인딩 → 재초안 진입
  draft_workflow:    'drafter',
  retry_draft:       'drafter',
  validate_workflow: 'validator',
  qa_evaluator:      'qa_eval',
  validation_failed: 'validator',
  qa_failed:         'qa_eval',
  promote:           'promote',
  save_workflow:     'promote',
  confirm_result:    'promote',
  save_memory:       'promote',
};

// agent_node 프레임 이름 → 표시 단계. 매핑 없으면 null(현재 단계 유지).
// skills_builder.* 릴레이 프레임(동적 이름: skills_builder.upsert.X 등)은 모두 'skill' 단계.
export function toStep(toolName: string): AgentStep | null {
  if (toolName in TOOL_TO_STEP) return TOOL_TO_STEP[toolName];
  if (toolName.startsWith('skills_builder.')) return 'skill';
  return null;
}

// agent_node 프레임 → 표시 단계. GUARD_ORDER 기준 **단조 증가만** 허용한다.
// supervisor↔composer 2-앱 핸드오프에서 SSE relay 순서가 뒤섞여(이슈 #297)
// 앞 단계 프레임(예: supervisor load_memory→security)이 뒤 단계(search_nodes→retriever)
// 이후 늦게 도착해도, 표시는 역행하지 않고 전진만 한다. 역행이면 prev 유지.
// 정당한 재방문(retry_draft→drafter, validation_failed→validator)은 같은 인덱스라 무해.
// 복합 흐름의 'skill'은 항상 index 0이라 이후 컴포저 단계가 역행하지 않는다.
// 미매핑 노드(composer 홉 마커 등)와 복구 silent 재시도의 재방출(security→…)도
// 역행 차단 대상이라 깜빡임 없이 표시가 유지된다.
export function nextMonotonicStep(prev: AgentStep | null, toolName: string): AgentStep | null {
  const mapped = toStep(toolName);
  // 미매핑 노드(composer/finalize 등 홉 마커)는 현재 단계를 **유지**한다.
  // 그대로 반영하면 page.tsx의 인덱스 계산이 0이 되어 스테퍼가 첫 단계로 리셋·역행한다.
  if (mapped === null) return prev;
  if (prev === null) return mapped;
  const mi = GUARD_ORDER.indexOf(mapped);
  const pi = GUARD_ORDER.indexOf(prev);
  return mi >= pi ? mapped : prev;
}

// ─── 검증 메시지 타임라인 — 사용자 표시용 4단계 요약 ───────────────────────────
// 디자인 SSOT: docs/검증메시지-구현가이드.md (claude.ai/design 핸드오프).
// 내부 7단계(보안·의도·검색·초안·검증·품질·확정)를 디자인의 4단계로 묶어 보여준다.
//   보안+의도 → 의도 분석 / 검색 → 노드 선출 / 초안+검증 → 워크플로우 작성 /
//   품질+확정 → 품질 평가. 복합 흐름이면 '스킬 생성'을 선두에 둔다.

export type VerifyPhase = 'skill' | 'intent' | 'select' | 'build' | 'qa';

const STEP_TO_PHASE: Record<AgentStep, VerifyPhase> = {
  skill: 'skill',
  security: 'intent',
  intent: 'intent',
  retriever: 'select',
  drafter: 'build',
  validator: 'build',
  qa_eval: 'qa',
  promote: 'qa',
};

const PHASE_BASE_ORDER: VerifyPhase[] = ['intent', 'select', 'build', 'qa'];

export const PHASE_TITLES: Record<VerifyPhase, string> = {
  skill: '스킬 생성',
  intent: '의도 분석',
  select: '노드 선출',
  build: '워크플로우 작성',
  qa: '품질 평가',
};

// 진행 단계에서 흐를 기본 안내 문구(SSE 판단근거 토큰이 없을 때 fallback).
const PHASE_HINTS: Record<VerifyPhase, string> = {
  skill: '스킬을 준비하고 있어요',
  intent: '요청을 분석하고 있어요',
  select: '필요한 노드를 찾고 있어요',
  build: '노드를 연결해 워크플로우를 만들고 있어요',
  qa: '품질을 점검하고 있어요',
};

export interface DisplayPhase {
  id: VerifyPhase;
  title: string;
  hint: string;
}

// 표시할 4(복합 시 5)단계 목록.
export function displayPhases(composite: boolean): DisplayPhase[] {
  const order = composite ? (['skill', ...PHASE_BASE_ORDER] as VerifyPhase[]) : [...PHASE_BASE_ORDER];
  return order.map((id) => ({ id, title: PHASE_TITLES[id], hint: PHASE_HINTS[id] }));
}

// 현재 내부 단계 → 표시 단계. 없으면 null(아직 미진입).
export function phaseFor(step: AgentStep | null): VerifyPhase | null {
  return step ? STEP_TO_PHASE[step] : null;
}
