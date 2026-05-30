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

// 4방향 핸들 공통 스타일. connectionMode=Loose 라 type 은 기본 방향 힌트일 뿐,
// 어느 핸들에서나 양방향 연결 가능. 같은 type 핸들이 2개 이상이면 React Flow 가
// 고유 id 를 요구하므로 변마다 id 부여('left'/'right'/'top'/'bottom').
const HANDLE_STYLE = { background: 'var(--color-ink)', width: 8, height: 8 } as const;

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
      <Handle id="left" type="target" position={RFPosition.Left} style={HANDLE_STYLE} />
      <Handle id="top" type="target" position={RFPosition.Top} style={HANDLE_STYLE} />
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
      <Handle id="right" type="source" position={RFPosition.Right} style={HANDLE_STYLE} />
      <Handle id="bottom" type="source" position={RFPosition.Bottom} style={HANDLE_STYLE} />
    </div>
  );
}
