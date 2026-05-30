import type { Edge as SchemaEdge } from '@common/generated';
import {
  toReactFlowEdge,
  resolveSourceHandle,
  resolveTargetHandle,
} from '../reactFlowAdapter';

function edge(from_handle: string, to_handle: string): SchemaEdge {
  return { from_instance_id: 'a', to_instance_id: 'b', from_handle, to_handle };
}

describe('reactFlowAdapter — 핸들 id 매핑', () => {
  describe('resolveSourceHandle', () => {
    it('레거시/AI 값 "output" 을 캔버스 핸들 "right" 로 매핑한다', () => {
      expect(resolveSourceHandle('output')).toBe('right');
    });

    it('빈 값/null 은 기본 source=right 로 폴백한다', () => {
      expect(resolveSourceHandle('')).toBe('right');
      expect(resolveSourceHandle(null)).toBe('right');
      expect(resolveSourceHandle(undefined)).toBe('right');
    });

    it('유효한 4방향 핸들 id 는 그대로 통과시킨다', () => {
      expect(resolveSourceHandle('top')).toBe('top');
      expect(resolveSourceHandle('bottom')).toBe('bottom');
      expect(resolveSourceHandle('left')).toBe('left');
      expect(resolveSourceHandle('right')).toBe('right');
    });

    it('알 수 없는 값은 기본 source=right 로 폴백한다', () => {
      expect(resolveSourceHandle('out')).toBe('right');
    });
  });

  describe('resolveTargetHandle', () => {
    it('레거시/AI 값 "input" 을 캔버스 핸들 "left" 로 매핑한다', () => {
      expect(resolveTargetHandle('input')).toBe('left');
    });

    it('빈 값/null 은 기본 target=left 로 폴백한다', () => {
      expect(resolveTargetHandle('')).toBe('left');
      expect(resolveTargetHandle(null)).toBe('left');
      expect(resolveTargetHandle(undefined)).toBe('left');
    });

    it('유효한 4방향 핸들 id 는 그대로 통과시킨다', () => {
      expect(resolveTargetHandle('top')).toBe('top');
      expect(resolveTargetHandle('bottom')).toBe('bottom');
      expect(resolveTargetHandle('left')).toBe('left');
      expect(resolveTargetHandle('right')).toBe('right');
    });

    it('알 수 없는 값은 기본 target=left 로 폴백한다', () => {
      expect(resolveTargetHandle('in')).toBe('left');
    });
  });

  describe('toReactFlowEdge — AI 생성 워크플로우 렌더 경로', () => {
    it('AI 드래프터의 output/input 엣지가 매칭되는 핸들 id 로 그려진다', () => {
      // 회귀 방지: 이전엔 sourceHandle="output" 로 새서 핸들 매칭 실패 → 엣지 미렌더.
      const rf = toReactFlowEdge(edge('output', 'input'));
      expect(rf.sourceHandle).toBe('right');
      expect(rf.targetHandle).toBe('left');
    });

    it('4방향 핸들 엣지(top→bottom)는 그대로 보존된다', () => {
      const rf = toReactFlowEdge(edge('bottom', 'top'));
      expect(rf.sourceHandle).toBe('bottom');
      expect(rf.targetHandle).toBe('top');
    });
  });
});
