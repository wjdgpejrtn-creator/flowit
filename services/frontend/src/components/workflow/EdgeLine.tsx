'use client';

import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from '@xyflow/react';
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
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 6,
  });
  const removeEdge = useWorkflowStore((s) => s.removeEdge);
  const stroke = selected ? 'var(--color-accent)' : 'var(--color-ink)';

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
        style={{ stroke, strokeWidth: selected ? 2.5 : 1.5 }}
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
