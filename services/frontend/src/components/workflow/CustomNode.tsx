import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { RiskLevel } from '@common/generated';

const RISK_COLORS: Record<string, string> = {
  [RiskLevel.LOW]:        'var(--color-risk-low)',
  [RiskLevel.MEDIUM]:     'var(--color-risk-med)',
  [RiskLevel.HIGH]:       'var(--color-risk-high)',
  [RiskLevel.RESTRICTED]: 'var(--color-risk-restricted)',
};

const STATUS_COLORS: Record<string, string> = {
  running:   'var(--color-status-running)',
  succeeded: 'var(--color-status-succeeded)',
  failed:    'var(--color-status-failed)',
  retrying:  'var(--color-status-retrying)',
  pending:   'var(--color-ink4)',
  cancelled: 'var(--color-ink4)',
};

interface CustomNodeData {
  label: string;
  icon?: string;
  riskLevel?: string;
  status?: string;
  locked?: boolean;
  [key: string]: unknown;
}

function CustomNode({ data, selected }: NodeProps) {
  const nodeData = data as CustomNodeData;
  const riskColor = nodeData.riskLevel ? (RISK_COLORS[nodeData.riskLevel] ?? 'var(--color-ink4)') : 'var(--color-ink4)';
  const statusColor = nodeData.status ? (STATUS_COLORS[nodeData.status] ?? 'var(--color-ink4)') : undefined;
  const isRunning = nodeData.status === 'running';

  return (
    <div
      className="relative border-[1.5px] border-[var(--color-ink)] rounded-[5px_9px_5px_9px] pl-3 pr-2 py-[5px] min-w-[110px] bg-[var(--color-surface)] text-[13px]"
      style={{
        boxShadow: selected
          ? `0 0 0 2px var(--color-accent), 2px 3px 0 var(--color-ink)`
          : statusColor
            ? `0 0 0 2px ${statusColor}, 2px 3px 0 var(--color-ink4)`
            : '2px 3px 0 var(--color-ink4)',
        opacity: nodeData.locked ? 0.7 : 1,
      }}
    >
      {/* 리스크 스트라이프 */}
      <span
        className="absolute left-0 top-1 bottom-1 w-1 rounded-r-sm"
        style={{ background: riskColor }}
      />

      <Handle type="target" position={Position.Left} style={{ background: 'var(--color-ink)', width: 8, height: 8, border: '1.5px solid var(--color-ink)' }} />

      <div className="flex items-center gap-1">
        {nodeData.icon && (
          <span className="inline-flex items-center justify-center w-[18px] h-[18px] border-[1.5px] border-[var(--color-ink)] rounded bg-[var(--color-paper2)] font-mono text-[11px] leading-none flex-shrink-0">
            {nodeData.icon}
          </span>
        )}
        <span className="font-bold leading-none truncate max-w-[80px]">{nodeData.label}</span>
        {nodeData.locked && <span className="text-[11px]">🔒</span>}
      </div>

      {nodeData.status && (
        <div
          className={`font-mono text-[9px] mt-[2px] ${isRunning ? 'animate-pulse' : ''}`}
          style={{ color: statusColor }}
        >
          {nodeData.status}
        </div>
      )}

      <Handle type="source" position={Position.Right} style={{ background: 'var(--color-ink)', width: 8, height: 8, border: '1.5px solid var(--color-ink)' }} />
    </div>
  );
}

export default memo(CustomNode);
