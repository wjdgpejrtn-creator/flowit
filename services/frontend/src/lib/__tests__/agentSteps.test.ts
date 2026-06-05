import {
  nextMonotonicStep,
  stepIndexFor,
  displayLabels,
  toStep,
  STEP_ORDER,
  TOOL_TO_STEP,
} from '../agentSteps';

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
      seen.push(STEP_ORDER.indexOf(step!));
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
    expect(STEP_ORDER.indexOf(nextMonotonicStep('retriever', 'suggest_skill_select')!) + 1).toBe(3);
  });

  it('미매핑 + prev=null이면 null을 반환(스테퍼 미점등 = 기존 0단계 동작)', () => {
    // composer/finalize 같은 홉 마커는 단계가 아니므로 표시를 바꾸지 않는다.
    expect(nextMonotonicStep(null, 'composer')).toBeNull();
    expect(nextMonotonicStep(null, 'finalize')).toBeNull();
  });
});

describe('복합 skill_then_compose — 선두 스킬 단계 (a)', () => {
  it('build_skill / skills_builder.* 릴레이는 모두 skill 단계로 매핑', () => {
    expect(toStep('build_skill')).toBe('skill');
    expect(toStep('skills_builder.load_functional_domain')).toBe('skill');
    expect(toStep('skills_builder.upsert.slack_message_sender')).toBe('skill');
  });

  it('skill 단계는 컴포저 파이프라인보다 앞 — 이후 단계가 역행하지 않는다', () => {
    // build_skill(skill) → composer(미매핑, 유지) → security → … 전진만
    let step = nextMonotonicStep(null, 'build_skill');
    expect(step).toBe('skill');
    step = nextMonotonicStep(step, 'skills_builder.upsert.x'); // 빌드 릴레이 — 유지
    expect(step).toBe('skill');
    step = nextMonotonicStep(step, 'composer');                // 홉 마커 — 유지
    expect(step).toBe('skill');
    step = nextMonotonicStep(step, 'security');                // 컴포저 진입 — 전진
    expect(step).toBe('security');
    step = nextMonotonicStep(step, 'search_nodes');
    expect(step).toBe('retriever');
  });

  it('지연 도착한 skill 릴레이 프레임도 컴포저 단계를 역행시키지 않는다', () => {
    // relay 순서 뒤섞임: 이미 retriever인데 skills_builder.* 가 늦게 도착
    expect(nextMonotonicStep('retriever', 'skills_builder.upsert.x')).toBe('retriever');
    expect(nextMonotonicStep('drafter', 'build_skill')).toBe('drafter');
  });

  it('stepIndexFor — 복합이면 skill 선두 포함, 비복합이면 컴포저 7단계 기준', () => {
    expect(stepIndexFor('skill', true)).toBe(1);
    expect(stepIndexFor('security', true)).toBe(2);   // skill 다음
    expect(stepIndexFor('security', false)).toBe(1);  // 비복합은 첫 단계
    expect(stepIndexFor('promote', false)).toBe(7);
    expect(stepIndexFor('promote', true)).toBe(8);
    expect(stepIndexFor(null, true)).toBe(0);
  });

  it('displayLabels — 복합이면 "스킬 생성"이 선두에 1칸 추가', () => {
    const base = displayLabels(false);
    const composite = displayLabels(true);
    expect(base[0]).toBe('보안 검토');
    expect(base).toHaveLength(7);
    expect(composite[0]).toBe('스킬 생성');
    expect(composite[1]).toBe('보안 검토');
    expect(composite).toHaveLength(8);
  });
});

describe('two-shot 2차 resume — 침묵 복귀 단계 매핑 (b)', () => {
  it('resume / bind_skill 가 단계로 매핑되어 재개 시 빈 단계가 없다', () => {
    // 백엔드가 진행 안내 메시지를 침묵 처리해도 composer→resume→bind_skill→draft 프레임으로 전진.
    expect(toStep('resume')).toBe('retriever');
    expect(toStep('bind_skill')).toBe('drafter');
  });

  it('새로고침 후 currentStep=null 재개 — composer(유지)→resume→bind_skill→draft 전진', () => {
    let step = nextMonotonicStep(null, 'composer');     // 홉 마커 — null 유지
    expect(step).toBeNull();
    step = nextMonotonicStep(step, 'resume');           // 노드 검색 상태 복원
    expect(step).toBe('retriever');
    step = nextMonotonicStep(step, 'bind_skill');       // 스킬 바인딩 → 초안
    expect(step).toBe('drafter');
    step = nextMonotonicStep(step, 'draft_workflow');
    expect(step).toBe('drafter');
  });

  it('같은 세션 재개 — round1 잔여 retriever 에서 이어져도 역행 없음', () => {
    // round1 끝 currentStep='retriever'(suggest_skill_select). round2 진입.
    let step: ReturnType<typeof nextMonotonicStep> = 'retriever';
    step = nextMonotonicStep(step, 'composer');         // 유지
    expect(step).toBe('retriever');
    step = nextMonotonicStep(step, 'resume');           // 같은 인덱스 — 유지
    expect(step).toBe('retriever');
    step = nextMonotonicStep(step, 'bind_skill');       // 전진
    expect(step).toBe('drafter');
  });
});

describe('복구 silent 재시도 — 재방출 역행 차단 (c)', () => {
  it('연결 실패 후 composer 재시작 재방출(security…)이 진행분을 역행시키지 않는다', () => {
    // 1차: search_nodes 까지 진행 후 content==0 사전연결 실패 → 백엔드 suppress + 재시도.
    // 2차 재방출은 컴포저 처음(security)부터 다시 흐른다. 표시는 retriever 유지(역행 X).
    const frames = ['security', 'intent', 'search_nodes', /* 재시도 재방출 */ 'security', 'intent', 'search_nodes', 'draft_workflow'];
    let step: ReturnType<typeof nextMonotonicStep> = null;
    const seen: number[] = [];
    for (const f of frames) {
      step = nextMonotonicStep(step, f);
      seen.push(STEP_ORDER.indexOf(step!));
    }
    for (let i = 1; i < seen.length; i++) {
      expect(seen[i]).toBeGreaterThanOrEqual(seen[i - 1]); // 단조 증가 — 깜빡임 없음
    }
    expect(step).toBe('drafter');
  });
});
