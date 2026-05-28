'use client';

import { Handle, Position as RFPosition, type NodeProps } from '@xyflow/react';
import NodeCard from '@/components/common/NodeCard';
import { RiskLevel } from '@common/generated';
import type { NodeStatus } from '@/types';
import { useWorkflowStore } from '@/stores/workflowStore';

export interface CustomNodeData {
  name: string;
  node_type: string;
  risk_level: RiskLevel;
  status?: NodeStatus;
  icon?: string;
  onDelete?: (id: string) => void;
}

export default function CustomNode({ id, data, selected }: NodeProps) {
  const d = data as unknown as CustomNodeData;
  const workflowRemoveNode = useWorkflowStore((s) => s.removeNode);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (d.onDelete) {
      d.onDelete(id);
    } else {
      workflowRemoveNode(id);
    }
  };

  return (
    <div className={`relative ${selected ? 'ring-2 ring-[var(--color-accent)] rounded-[5px_9px_5px_9px]' : ''}`}>
      <Handle
        type="target"
        position={RFPosition.Left}
        style={{ background: 'var(--color-ink)', width: 8, height: 8 }}
      />
      <NodeCard
        icon={d.icon ?? d.name.slice(0, 1).toUpperCase()}
        name={d.name}
        risk={d.risk_level}
        status={d.status}
        meta={d.node_type}
      />
      {selected && (
        <button
          type="button"
          onClick={handleDelete}
          onMouseDown={(e) => e.stopPropagation()}
          aria-label="노드 삭제"
          title="노드 삭제"
          data-testid={`custom-node-delete-${id}`}
          className="nodrag absolute -top-2 -right-2 w-[20px] h-[20px] rounded-full bg-[var(--color-status-failed)] text-white text-[14px] leading-none flex items-center justify-center border-[1.5px] border-[var(--color-ink)] cursor-pointer hover:bg-red-700"
        >
          ×
        </button>
      )}
      <Handle
        type="source"
        position={RFPosition.Right}
        style={{ background: 'var(--color-ink)', width: 8, height: 8 }}
      />
    </div>
  );
}
