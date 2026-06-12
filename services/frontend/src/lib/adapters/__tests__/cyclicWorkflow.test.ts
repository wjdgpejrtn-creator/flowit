import type { Edge as SchemaEdge } from '@common/generated';
import { buildEdgeId, resolveSourceHandle, resolveTargetHandle } from '../reactFlowAdapter';

// §6.6 quality_loop 스켈레톤이 내보내는 순환 워크플로우(검증→재생성 back-edge)의 엣지 집합.
// 백엔드 조립기(ai_agent/domain/services/skeleton_assembler.py `_assemble_*`)가 emit 하는
// 핸들 규약 그대로:
//   generator(ai) → scorer(llm_judge) → evaluator(if_condition)
//   evaluator → generator  (from_handle="false", 재생성 back-edge)   ← SCC, 사이클
//   evaluator → sink       (from_handle="true",  통과 분기)
// WorkflowCanvas.rfEdges 가 쓰는 함수와 동일 경로로 검증한다(인라인 빌드 → 단일 소스 미러).
function ed(
  from_instance_id: string,
  to_instance_id: string,
  from_handle = 'output',
  to_handle = 'input',
): SchemaEdge {
  return { from_instance_id, to_instance_id, from_handle, to_handle };
}

const QUALITY_LOOP_EDGES: SchemaEdge[] = [
  ed('trigger', 'source'),
  ed('source', 'generator'),
  ed('generator', 'scorer'),
  ed('scorer', 'evaluator'),
  ed('evaluator', 'generator', 'false'), // back-edge (재생성)
  ed('evaluator', 'sink', 'true'), // 통과 분기
];

// WorkflowCanvas.tsx 의 rfEdges useMemo 와 동일 변환(인라인 로직 미러).
function toRfEdges(edges: SchemaEdge[]) {
  return edges.map((e) => ({
    id: buildEdgeId(e),
    source: e.from_instance_id,
    target: e.to_instance_id,
    sourceHandle: resolveSourceHandle(e.from_handle),
    targetHandle: resolveTargetHandle(e.to_handle),
  }));
}

describe('순환 워크플로우(quality_loop) 렌더 경로', () => {
  it('back-edge 포함 사이클이 데이터 레이어에서 표현 가능하다 — 엣지 id 충돌·누락 없음', () => {
    const rf = toRfEdges(QUALITY_LOOP_EDGES);
    // 모든 엣지가 고유 id (back-edge evaluator→generator 도 spine 과 안 겹침)
    const ids = rf.map((e) => e.id);
    expect(new Set(ids).size).toBe(QUALITY_LOOP_EDGES.length);
    // 모든 핸들이 유효한 4방향 id 로 해소 (React Flow 가 핸들 매칭 실패로 엣지를 버리지 않음)
    const valid = new Set(['left', 'right', 'top', 'bottom']);
    for (const e of rf) {
      expect(valid.has(e.sourceHandle)).toBe(true);
      expect(valid.has(e.targetHandle)).toBe(true);
    }
  });

  it('back-edge(evaluator→generator)가 spine 의 generator 를 target 으로 되짚는다 — 사이클 형성', () => {
    const rf = toRfEdges(QUALITY_LOOP_EDGES);
    const back = rf.find((e) => e.source === 'evaluator' && e.target === 'generator');
    const forward = rf.find((e) => e.source === 'generator');
    expect(back).toBeDefined();
    expect(forward).toBeDefined();
    // generator 는 들어오는 엣지(source/back-edge)와 나가는 엣지를 동시에 가짐 = SCC 노드
    expect(back!.target).toBe(forward!.source);
  });

  // ⚠️ 알려진 갭 (Phase 2 발견) — condition(if_condition) 분기 시각 미구분.
  // 백엔드는 통과=from_handle "true", 재생성/반려=from_handle "false" 로 두 갈래를 구분해 emit
  // 하지만, resolveSourceHandle 이 "true"/"false" 를 모르는 값으로 보고 둘 다 "right" 로 폴백한다
  // (CANVAS_HANDLE_IDS = {left,right,top,bottom} 만 통과). 결과: true 분기와 false back-edge 가
  // 같은 핸들에서 출발 → 시각적으로 구분 불가, 분기 라벨 없음.
  // 후속 수정(true→예: bottom/coral, false→예: top/회색 + EdgeLine 라벨) 시 이 테스트를 갱신할 것.
  it('[KNOWN GAP] condition true/false 분기가 같은 source 핸들로 붕괴된다(구분 안 됨)', () => {
    expect(resolveSourceHandle('true')).toBe('right');
    expect(resolveSourceHandle('false')).toBe('right');
    // 두 분기가 동일 핸들 → 시각 구분 불가
    expect(resolveSourceHandle('true')).toBe(resolveSourceHandle('false'));
  });
});
