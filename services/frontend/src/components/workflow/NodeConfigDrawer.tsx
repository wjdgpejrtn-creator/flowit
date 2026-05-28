'use client';

import { useState } from 'react';
import Btn from '@/components/common/Btn';
import RiskLevelBadge from './RiskLevelBadge';
import type { NodeInstance, NodeConfig } from '@common/generated';

interface Props {
  node: NodeInstance | null;
  catalog: NodeConfig | null;
  onClose: () => void;
  onSave: (updated: NodeInstance) => void;
}

export default function NodeConfigDrawer({ node, catalog, onClose, onSave }: Props) {
  const [params, setParams] = useState<Record<string, unknown>>(node?.parameters ?? {});

  if (!node) return null;

  const handleSave = () => {
    onSave({ ...node, parameters: params });
    onClose();
  };

  return (
    <div
      className="fixed top-0 right-0 h-full w-[320px] bg-[var(--color-surface)] border-l-[1.5px] border-[var(--color-ink)] flex flex-col z-50 shadow-lg"
      style={{ boxShadow: '-3px 0 0 var(--color-ink)' }}
    >
      {/* 헤더 */}
      <div className="flex items-center gap-2 px-4 py-3 border-b-[1.5px] border-[var(--color-ink)]">
        <div className="flex-1 min-w-0">
          <div className="font-bold text-[13px] truncate">{catalog?.name ?? node.node_id}</div>
          <div className="text-[11px] text-[var(--color-ink3)] font-mono mt-[1px]">
            {node.instance_id.slice(0, 8)}…
          </div>
        </div>
        {catalog && <RiskLevelBadge level={catalog.risk_level} />}
        <button
          onClick={onClose}
          className="text-[14px] text-[var(--color-ink3)] hover:text-[var(--color-ink)] bg-transparent border-none cursor-pointer"
        >
          ✕
        </button>
      </div>

      {/* 설명 */}
      {catalog?.description && (
        <div className="px-4 py-2 border-b border-[var(--color-line-soft)] text-[12px] text-[var(--color-ink3)]">
          {catalog.description}
        </div>
      )}

      {/* 파라미터 편집 */}
      <div className="flex-1 overflow-auto px-4 py-3 flex flex-col gap-3">
        <div className="text-[11px] font-bold text-[var(--color-ink3)] uppercase tracking-wider">파라미터</div>
        {Object.keys(params).length === 0 ? (
          <p className="text-[12px] text-[var(--color-ink4)] italic">설정할 파라미터가 없습니다.</p>
        ) : (
          Object.entries(params).map(([key, val]) => (
            <div key={key} className="flex flex-col gap-1">
              <label className="text-[11px] font-bold text-[var(--color-ink3)] font-mono">{key}</label>
              <input
                type="text"
                value={String(val ?? '')}
                onChange={(e) => setParams((prev) => ({ ...prev, [key]: e.target.value }))}
                className="border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-2 py-[4px] text-[12px] bg-[var(--color-paper)] focus:outline-none focus:border-[var(--color-accent)]"
              />
            </div>
          ))
        )}

        {/* 필수 연결 */}
        {catalog && catalog.required_connections.length > 0 && (
          <div className="mt-2">
            <div className="text-[11px] font-bold text-[var(--color-ink3)] uppercase tracking-wider mb-1">필수 연결</div>
            {catalog.required_connections.map((c) => (
              <div key={c} className="text-[11px] font-mono text-[var(--color-ink3)] flex items-center gap-1">
                <span className="text-[var(--color-risk-restricted)]">*</span> {c}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 액션 */}
      <div className="px-4 py-3 border-t-[1.5px] border-[var(--color-ink)] flex gap-2">
        <Btn primary onClick={handleSave} className="flex-1 justify-center">저장</Btn>
        <Btn ghost onClick={onClose}>취소</Btn>
      </div>
    </div>
  );
}
