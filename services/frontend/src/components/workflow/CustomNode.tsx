'use client';

import { Handle, Position as RFPosition, type NodeProps } from '@xyflow/react';
import Icon from '@/components/common/Icon';
import RiskPill from '@/components/common/RiskPill';
import { RiskLevel } from '@common/generated';
import type { NodeStatus } from '@/types';
import { useWorkflowStore } from '@/stores/workflowStore';
import { resolveNodeIcon } from '@/lib/nodeIcon';

export interface CustomNodeData {
  name: string;
  node_type: string;
  risk_level: RiskLevel;
  status?: NodeStatus;
  /** 명시 아이콘(kebab-case lucide). 미지정 시 node_type 으로 추론 */
  icon?: string;
  category?: string;
  onDelete?: (id: string) => void;
}

/**
 * 시안(Flowit.html) 노드 카드 디자인을 React Flow 커스텀 노드로 포팅.
 * 220×56 흰 카드 + 32px 아이콘박스(#F7F1E8) + lucide 아이콘 + 노드명/타입 + 우측 위험도 pill.
 * 포트 4개는 .flowit-handle (globals.css) 로 12px 흰 원·hover 시 coral·1.3배.
 * connectionMode=Loose 라 어느 핸들에서나 양방향 연결 가능 — 변마다 고유 id 부여.
 */
export default function CustomNode({ id, data, selected }: NodeProps) {
  const d = data as unknown as CustomNodeData;
  const workflowRemoveNode = useWorkflowStore((s) => s.removeNode);
  const { icon, color } = d.icon
    ? { icon: d.icon, color: 'var(--color-accent)' }
    : resolveNodeIcon(d.node_type, d.category);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (d.onDelete) d.onDelete(id);
    else workflowRemoveNode(id);
  };

  const ring = selected
    ? 'border-[var(--color-accent)] ring-2 ring-[var(--color-accent)]/20'
    : 'border-[var(--color-line-soft)] hover:border-[var(--color-accent)]';

  return (
    <div
      className={[
        'group relative w-[220px] h-[56px] bg-white border rounded-xl p-2',
        'flex items-center gap-2.5 shadow-sm hover:shadow-md transition-shadow',
        ring,
      ].join(' ')}
    >
      <Handle id="top" type="target" position={RFPosition.Top} className="flowit-handle" />
      <Handle id="left" type="target" position={RFPosition.Left} className="flowit-handle" />

      {/* 아이콘 박스 */}
      <div className="w-8 h-8 rounded-lg bg-[#F7F1E8] flex items-center justify-center border border-[var(--color-line-soft)] flex-shrink-0">
        <Icon name={icon} className="w-4 h-4" style={{ color }} />
      </div>

      {/* 이름 / 타입 */}
      <div className="overflow-hidden flex-1 min-w-0">
        <span className="text-xs font-bold text-[var(--color-ink)] truncate block leading-tight">
          {d.name}
        </span>
        <span className="text-[9px] font-mono text-[var(--color-ink3)] block leading-tight truncate">
          {d.node_type}
        </span>
      </div>

      {/* 위험도 pill */}
      <div className="flex-shrink-0">
        <RiskPill level={d.risk_level} />
      </div>

      {/* hover 삭제 버튼 */}
      <button
        type="button"
        onClick={handleDelete}
        onMouseDown={(e) => e.stopPropagation()}
        aria-label="노드 삭제"
        title="노드 삭제"
        data-testid={`custom-node-delete-${id}`}
        className="nodrag absolute -top-3 -right-3 w-7 h-7 flex items-center justify-center rounded-full opacity-0 group-hover:opacity-100 bg-white border border-[var(--color-line-soft)] shadow-md text-[var(--color-ink4)] hover:bg-red-50 hover:border-red-300 hover:text-red-500 transition-all"
      >
        <Icon name="x" className="w-3.5 h-3.5" />
      </button>

      <Handle id="right" type="source" position={RFPosition.Right} className="flowit-handle" />
      <Handle id="bottom" type="source" position={RFPosition.Bottom} className="flowit-handle" />
    </div>
  );
}
