'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { getCatalog } from '@/lib/api/nodeApi';
import {
  updateWorkflow,
  validateWorkflow,
  executeWorkflow,
  type ExecuteResponse,
} from '@/lib/api/workflowApi';
import { useWorkflowStore } from '@/stores/workflowStore';
import type { NodeConfig, WorkflowSchema } from '@common/generated';
import Btn from '@/components/common/Btn';
import ErrorBanner from '@/components/common/ErrorBanner';
import WorkflowCanvas from './WorkflowCanvas';
import NodeConfigDrawer from './NodeConfigDrawer';
import ValidationPanel from './ValidationPanel';

export interface MissingRequiredEntry {
  instance_id: string;
  node_name: string;
  fields: string[];
}

/**
 * 워크플로우의 각 노드를 카탈로그와 대조하여 input_schema.required 중 비어있는 필드를 모은다.
 * Backend GraphValidator가 parameter required를 검사하지 않으므로 frontend 가드.
 */
export function computeMissingRequired(
  workflow: WorkflowSchema | null,
  catalog: NodeConfig[] | null,
): MissingRequiredEntry[] {
  if (!workflow || !catalog) return [];
  const byNodeId = new Map(catalog.map((c) => [c.node_id, c]));
  const result: MissingRequiredEntry[] = [];
  for (const node of workflow.nodes) {
    const cfg = byNodeId.get(node.node_id);
    if (!cfg) continue;
    const schema = cfg.input_schema as { required?: string[] } | undefined;
    const required = schema?.required ?? [];
    if (required.length === 0) continue;
    const params = (node.parameters as Record<string, unknown>) ?? {};
    const missing = required.filter((field) => {
      const v = params[field];
      return v === undefined || v === null || v === '';
    });
    if (missing.length > 0) {
      result.push({ instance_id: node.instance_id, node_name: cfg.name, fields: missing });
    }
  }
  return result;
}

export function stripInternalParams(workflow: WorkflowSchema): WorkflowSchema {
  return {
    ...workflow,
    nodes: workflow.nodes.map((n) => {
      const { __palette: _ignored, ...rest } = (n.parameters as Record<string, unknown> & {
        __palette?: unknown;
      });
      return { ...n, parameters: rest };
    }),
  };
}

/**
 * Save 후 서버 응답 워크플로우에 클라이언트 전용 __palette 메타를 재주입한다.
 * 인덱스가 아닌 `instance_id` 매칭으로 — 서버가 노드 순서 재정렬해도 안전.
 */
export function rehydratePaletteMetadata(
  saved: WorkflowSchema,
  previous: WorkflowSchema,
): WorkflowSchema {
  const paletteByInstanceId = new Map<string, unknown>();
  for (const n of previous.nodes) {
    const meta = (n.parameters as { __palette?: unknown } | undefined)?.__palette;
    if (meta !== undefined) paletteByInstanceId.set(n.instance_id, meta);
  }
  return {
    ...saved,
    nodes: saved.nodes.map((n) => {
      const meta = paletteByInstanceId.get(n.instance_id);
      if (meta === undefined) return n;
      return {
        ...n,
        parameters: {
          ...(n.parameters as Record<string, unknown>),
          __palette: meta,
        },
      };
    }),
  };
}

interface Props {
  onExecuted?: (resp: ExecuteResponse) => void;
}

export default function WorkflowEditPane({ onExecuted }: Props) {
  const workflow = useWorkflowStore((s) => s.workflow);
  const dirty = useWorkflowStore((s) => s.dirty);
  const setWorkflow = useWorkflowStore((s) => s.setWorkflow);
  const setValidationErrors = useWorkflowStore((s) => s.setValidationErrors);
  const setSelectedNodeId = useWorkflowStore((s) => s.setSelectedNodeId);
  const markClean = useWorkflowStore((s) => s.markClean);

  const [catalog, setCatalog] = useState<NodeConfig[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getCatalog();
        if (!cancelled) setCatalog(data);
      } catch (e) {
        if (!cancelled) setActionError(e instanceof Error ? e.message : '카탈로그 조회 실패');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const missingRequired = useMemo(
    () => computeMissingRequired(workflow, catalog),
    [workflow, catalog],
  );
  const totalMissingFields = useMemo(
    () => missingRequired.reduce((n, m) => n + m.fields.length, 0),
    [missingRequired],
  );

  const handleSave = useCallback(async (): Promise<WorkflowSchema | null> => {
    if (!workflow) return null;
    setBusy(true);
    setActionError(null);
    setActionMsg(null);
    try {
      const payload = stripInternalParams(workflow);
      const saved = await updateWorkflow(String(workflow.workflow_id), payload);
      setWorkflow(rehydratePaletteMetadata(saved, workflow));
      markClean();
      setActionMsg('저장 완료');
      return saved;
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '저장 실패');
      return null;
    } finally {
      setBusy(false);
    }
  }, [workflow, setWorkflow, markClean]);

  const handleValidate = useCallback(async () => {
    if (!workflow) return;
    setBusy(true);
    setActionError(null);
    setActionMsg(null);
    try {
      const result = await validateWorkflow(String(workflow.workflow_id));
      setValidationErrors(result.errors ?? []);
      setActionMsg(
        result.validation_status === 'passed'
          ? '검증 통과'
          : `검증 실패 (${result.errors?.length ?? 0}건)`,
      );
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '검증 요청 실패');
    } finally {
      setBusy(false);
    }
  }, [workflow, setValidationErrors]);

  const handleExecute = useCallback(async () => {
    if (!workflow) return;
    setBusy(true);
    setActionError(null);
    setActionMsg(null);
    try {
      if (dirty) {
        const saved = await handleSave();
        if (!saved) return;
      }
      const resp = await executeWorkflow(String(workflow.workflow_id));
      setActionMsg(`실행 시작 (${resp.execution_id.slice(0, 8)}…)`);
      onExecuted?.(resp);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '실행 요청 실패');
    } finally {
      setBusy(false);
    }
  }, [workflow, dirty, handleSave, onExecuted]);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div
        className="flex items-center gap-2 px-3 py-[6px] border-b-[1.5px] border-[var(--color-line-soft)]"
        style={{ background: 'var(--color-paper2)' }}
      >
        <span className="text-[12px] text-[var(--color-ink3)]">편집 모드</span>
        {dirty && (
          <span className="text-[11px] px-[6px] py-[1px] border-[1.5px] border-[var(--color-status-retrying)] rounded-full text-[var(--color-status-retrying)] font-bold">
            ● 미저장 변경
          </span>
        )}
        {actionMsg && (
          <span className="text-[11px] text-[var(--color-status-succeeded)] font-mono">
            {actionMsg}
          </span>
        )}
        {missingRequired.length > 0 && (
          <button
            type="button"
            onClick={() => setSelectedNodeId(missingRequired[0].instance_id)}
            data-testid="missing-required-banner"
            title="클릭하면 첫 누락 노드를 선택합니다"
            className="text-[11px] text-[var(--color-status-failed)] font-bold border-[1.5px] border-[var(--color-status-failed)] rounded px-2 py-[1px] hover:bg-[var(--color-status-failed)] hover:text-white cursor-pointer"
          >
            ⚠ 필수 입력 누락: {missingRequired.length}노드 {totalMissingFields}건
            {' ('}
            {missingRequired
              .slice(0, 2)
              .map((m) => `${m.node_name}: ${m.fields.join(',')}`)
              .join(' / ')}
            {missingRequired.length > 2 ? ' …' : ''}
            {')'}
          </button>
        )}
        <div className="flex-1" />
        <Btn ghost onClick={() => void handleValidate()} disabled={busy || !workflow}>
          ✓ 검증
        </Btn>
        <Btn ghost onClick={() => void handleSave()} disabled={busy || !workflow || !dirty}>
          💾 저장
        </Btn>
        <Btn
          onClick={() => void handleExecute()}
          disabled={busy || !workflow || missingRequired.length > 0}
          title={
            missingRequired.length > 0
              ? '필수 입력이 누락된 노드가 있어 실행할 수 없습니다.'
              : undefined
          }
        >
          ▶ 실행
        </Btn>
      </div>

      {actionError && (
        <div className="px-3 pt-2">
          <ErrorBanner>
            <span>⚠ {actionError}</span>
          </ErrorBanner>
        </div>
      )}

      <div className="flex-1 flex min-h-0">
        <WorkflowCanvas catalog={catalog} />
        <NodeConfigDrawer catalog={catalog} />
      </div>

      <ValidationPanel />
    </div>
  );
}
