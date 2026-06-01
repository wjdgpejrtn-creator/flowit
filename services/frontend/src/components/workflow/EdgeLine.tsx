'use client';

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
  // 시안: 베지어 곡선 연결선. 평상시 점선(#D8CBB8), 선택 시 coral.
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const removeEdge = useWorkflowStore((s) => s.removeEdge);
  const stroke = selected ? 'var(--color-accent-coral)' : '#D8CBB8';

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    const [from, to] = id.split('->');
    if (from && to) removeEdge(from, to);
  };

  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        style={{ stroke, strokeWidth: 2, strokeDasharray: '4 4' }}
      />
      {selected && (
        <EdgeLabelRenderer>
          <button
            type="button"
            onClick={handleDelete}
            onMouseDown={(e) => e.stopPropagation()}
            aria-label="엣지 삭제"
            title="엣지 삭제"
            data-testid={`edge-delete-${id}`}
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="nodrag nopan w-[20px] h-[20px] rounded-full bg-[var(--color-status-failed)] text-white text-[14px] leading-none flex items-center justify-center border-[1.5px] border-[var(--color-ink)] cursor-pointer hover:bg-red-700"
          >
            ×
          </button>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
