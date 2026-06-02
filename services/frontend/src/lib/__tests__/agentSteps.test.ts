import { nextMonotonicStep, STEP_ORDER, TOOL_TO_STEP } from '../agentSteps';

describe('nextMonotonicStep — 단계 단조 증가 가드 (#297 역행 방지)', () => {
  it('prev=null이면 매핑 결과를 그대로 반환', () => {
    expect(nextMonotonicStep(null, 'security')).toBe('security');
    expect(nextMonotonicStep(null, 'search_nodes')).toBe('retriever');
  });

  it('전진(앞→뒤 단계)은 반영한다', () => {
    expect(nextMonotonicStep('security', 'intent')).toBe('intent');
    expect(nextMonotonicStep('intent', 'search_nodes')).toBe('retriever');
    expect(nextMonotonicStep('retriever', 'draft_workflow')).toBe('drafter');
  });

  it('역행(뒤→앞 단계)은 무시하고 prev를 유지한다 — 핵심 시나리오', () => {
    // 노드검색(retriever) 후 supervisor load_memory(→security)가 늦게 도착해도 역행 안 함
    expect(nextMonotonicStep('retriever', 'load_memory')).toBe('retriever');
    expect(nextMonotonicStep('retriever', 'security')).toBe('retriever');
    expect(nextMonotonicStep('promote', 'security')).toBe('promote');
  });

  it('동일 인덱스(정당한 재방문)는 그대로 유지 — retry/validation_failed 무해', () => {
    // retry_draft, validation_failed는 각각 drafter, validator로 같은 인덱스
    expect(nextMonotonicStep('drafter', 'retry_draft')).toBe('drafter');
    expect(nextMonotonicStep('validator', 'validation_failed')).toBe('validator');
    expect(nextMonotonicStep('qa_eval', 'qa_failed')).toBe('qa_eval');
  });

  it('역순 프레임 시퀀스 전체 — currentStep은 단조 증가만', () => {
    // search_nodes(retriever) 이후 supervisor 프레임이 뒤섞여 도착하는 실제 패턴
    const frames = ['security', 'intent', 'search_nodes', 'load_memory', 'analyze_intent', 'draft_workflow'];
    let step: ReturnType<typeof nextMonotonicStep> | null = null;
    const seen: number[] = [];
    for (const f of frames) {
      step = nextMonotonicStep(step, f);
      seen.push(STEP_ORDER.indexOf(step));
    }
    // 인덱스가 한 번도 감소하지 않아야 함
    for (let i = 1; i < seen.length; i++) {
      expect(seen[i]).toBeGreaterThanOrEqual(seen[i - 1]);
    }
    // 최종 단계는 drafter (가장 앞선 단계 유지)
    expect(step).toBe('drafter');
  });

  it('STEP_ORDER 밖 미매핑 노드는 현재 단계를 유지한다 (역행/리셋 방지)', () => {
    // 미매핑 노드를 그대로 반영하면 page.tsx의 indexOf+1=0 → 보안 검토로 리셋되는 버그.
    expect(TOOL_TO_STEP['unknown_node']).toBeUndefined();
    expect(nextMonotonicStep('retriever', 'unknown_node')).toBe('retriever');
  });

  it('suggest_skill_select는 노드 검색(retriever) 단계로 매핑 — 보안 검토 역행 버그 회귀 방지', () => {
    // 실제 함정: 노드 검색 후 suggest_skill_select 프레임이 미매핑이라 스테퍼가 보안 검토로
    // 역행하고 멈췄다(ground truth: ...search_nodes → suggest_skill_select → skill_selection).
    expect(TOOL_TO_STEP['suggest_skill_select']).toBe('retriever');
    expect(nextMonotonicStep('retriever', 'suggest_skill_select')).toBe('retriever');
    // page.tsx의 stepIndex 계산이 0으로 떨어지지 않음을 보장
    expect(STEP_ORDER.indexOf(nextMonotonicStep('retriever', 'suggest_skill_select')) + 1).toBe(3);
  });
});
