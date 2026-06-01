import type { AgentStep } from '@/stores/agentStore';

// 컨펌 게이트 파이프라인 단계 표시 — agent_node 프레임 ↔ 사용자 표시 단계 매핑/순서.
// page.tsx에서 분리(순수 로직 단위 테스트 가능).

export const STEP_ORDER: AgentStep[] = [
  'security', 'intent', 'retriever', 'drafter', 'validator', 'qa_eval', 'promote',
];

export const TOOL_TO_STEP: Record<string, AgentStep> = {
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

export const STEP_LABELS: Record<AgentStep, string> = {
  security:  '보안 검토',
  intent:    '의도 분류',
  retriever: '노드 검색',
  drafter:   '초안 생성',
  validator: '그래프 검증',
  qa_eval:   '품질 평가',
  promote:   '워크플로우 확정',
};

// agent_node 프레임 → 표시 단계. STEP_ORDER 기준 **단조 증가만** 허용한다.
// supervisor↔composer 2-앱 핸드오프에서 SSE relay 순서가 뒤섞여(이슈 #297)
// 앞 단계 프레임(예: supervisor load_memory→security)이 뒤 단계(search_nodes→retriever)
// 이후 늦게 도착해도, 표시는 역행하지 않고 전진만 한다. 역행이면 prev 유지.
// 정당한 재방문(retry_draft→drafter, validation_failed→validator)은 같은 인덱스라 무해.
export function nextMonotonicStep(prev: AgentStep | null, toolName: string): AgentStep {
  const mapped = TOOL_TO_STEP[toolName] ?? (toolName as AgentStep);
  if (prev === null) return mapped;
  const mi = STEP_ORDER.indexOf(mapped);
  const pi = STEP_ORDER.indexOf(prev);
  // 매핑 안 되는 단계(mi<0)는 STEP_ORDER 밖 — 가드 없이 그대로 반영.
  if (mi < 0) return mapped;
  return mi >= pi ? mapped : prev;
}
