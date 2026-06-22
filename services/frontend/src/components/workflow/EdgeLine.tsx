'use client';

import { useState } from 'react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from '@xyflow/react';
import { useWorkflowStore } from '@/stores/workflowStore';

export default function EdgeLine(props: EdgeProps) {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    markerEnd,
    selected,
  } = props;
  // 시안: 베지어 곡선 연결선. 평상시 점선(#D8CBB8), 선택/hover 시 coral + 중앙 삭제 버튼.
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const removeEdge = useWorkflowStore((s) => s.removeEdge);
  const [hovered, setHovered] = useState(false);
  const active = selected || hovered;
  const stroke = active ? 'var(--color-accent-coral)' : '#D8CBB8';

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    removeEdge(id);
  };

  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        style={{ stroke, strokeWidth: 2, strokeDasharray: '4 4' }}
      />
      {/* hover 감지용 투명 와이드 패스 — 얇은 점선의 적중 영역 확장 */}
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        style={{ cursor: 'pointer' }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      {active && (
        <EdgeLabelRenderer>
          <button
            type="button"
            onClick={handleDelete}
            onMouseDown={(e) => e.stopPropagation()}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            aria-label="엣지 삭제"
            title="엣지 삭제"
            data-testid={`edge-delete-${id}`}
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="nodrag nopan w-[20px] h-[20px] rounded-full bg-white text-[var(--color-accent-coral)] text-[14px] leading-none flex items-center justify-center border-[1.5px] border-[var(--color-accent-coral)] shadow-sm cursor-pointer hover:bg-[var(--color-accent-coral)] hover:text-white"
          >
            ×
          </button>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
