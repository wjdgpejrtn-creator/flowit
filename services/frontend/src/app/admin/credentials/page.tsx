'use client';

import { useEffect, useMemo, useState } from 'react';
import Icon from '@/components/common/Icon';
import Skel from '@/components/common/Skel';
import { listCredentialAudit, type CredentialAuditEntry } from '@/lib/api/credentialApi';

type FilterKey = 'all' | 'active' | 'revoked';

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'active', label: '활성' },
  { key: 'revoked', label: '해지' },
];

const SERVICE_LABEL: Record<string, string> = { google: 'Google', slack: 'Slack' };

function serviceName(c: CredentialAuditEntry): string {
  const svc = SERVICE_LABEL[c.service] ?? c.service;
  const tail = c.display_name || c.account_id;
  return tail ? `${svc} · ${tail}` : svc;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('ko-KR', { year: '2-digit', month: '2-digit', day: '2-digit' });
}

function errorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : '';
  if (msg.startsWith('401')) return '로그인이 만료되었습니다.';
  if (msg.startsWith('403')) return '관리자만 접근할 수 있습니다.';
  if (msg.startsWith('5')) return '서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.';
  if (msg === 'Failed to fetch' || msg === 'Load failed') return '네트워크 연결을 확인해 주세요.';
  return '자격증명 목록을 불러올 수 없습니다.';
}

export default function AdminCredentialsPage() {
  const [rows, setRows] = useState<CredentialAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchKey, setFetchKey] = useState(0);
  const [filter, setFilter] = useState<FilterKey>('all');

  useEffect(() => {
    setLoading(true);
    setError(null);
    listCredentialAudit()
      .then(setRows)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, [fetchKey]);

  const counts = useMemo(
    () => ({
      all: rows.length,
      active: rows.filter((r) => r.is_active).length,
      revoked: rows.filter((r) => !r.is_active).length,
    }),
    [rows],
  );

  const filtered = useMemo(() => {
    if (filter === 'active') return rows.filter((r) => r.is_active);
    if (filter === 'revoked') return rows.filter((r) => !r.is_active);
    return rows;
  }, [rows, filter]);

  return (
    <div className="max-w-[1200px]">
      <div className="border-b border-[var(--color-line-soft)] pb-3 mb-4">
        <h1 className="text-lg font-bold text-[var(--color-ink)]">자격증명 감사</h1>
        <p className="text-xs text-[var(--color-ink3)] mt-0.5">전사 OAuth 연결 추적 · 소유자·부서별</p>
      </div>

      {/* 필터 알약 탭 */}
      <div className="flex gap-1 mb-4">
        {FILTERS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={[
              'rounded-lg px-4 py-1.5 text-xs font-bold transition-colors',
              key === filter
                ? 'bg-[var(--color-accent)] text-white shadow-sm'
                : 'text-[var(--color-ink3)] hover:text-[var(--color-ink)] hover:bg-white/40',
            ].join(' ')}
          >
            {label} ({counts[key]})
          </button>
        ))}
      </div>

      {loading ? (
        <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl shadow-sm p-4 space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <Skel key={i} h={28} />
          ))}
        </div>
      ) : error ? (
        <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl p-8 text-center shadow-sm flex flex-col items-center gap-2">
          <p className="text-sm font-bold text-[var(--color-danger)]">{error}</p>
          <button
            type="button"
            onClick={() => setFetchKey((k) => k + 1)}
            className="text-xs px-3 py-1.5 rounded-lg border border-[var(--color-line-soft)] bg-white font-bold hover:bg-[var(--color-paper)]"
          >
            다시 시도
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl p-8 text-center shadow-sm">
          <p className="text-sm font-bold text-[var(--color-ink)]">표시할 자격증명이 없습니다.</p>
        </div>
      ) : (
        <div className="bg-white border border-[var(--color-line-soft)] rounded-2xl shadow-sm overflow-hidden">
          {/* 헤더 */}
          <div className="grid grid-cols-12 px-4 py-3 border-b border-[var(--color-line-soft)] text-[11px] font-bold uppercase tracking-wide text-[var(--color-ink3)]">
            <span className="col-span-3">이름</span>
            <span className="col-span-3">소유자</span>
            <span className="col-span-2">부서</span>
            <span className="col-span-2">권한</span>
            <span className="col-span-2">상태 · 연결일</span>
          </div>

          <div className="divide-y divide-[var(--color-line-soft)]">
            {filtered.map((cred) => (
              <div
                key={cred.oauth_id}
                className="grid grid-cols-12 px-4 py-4 items-center hover:bg-[var(--color-hl)]/40 transition-colors"
              >
                <span className="col-span-3 font-bold text-[13px] text-[var(--color-ink)]">
                  {serviceName(cred)}
                </span>
                <span className="col-span-3 text-[13px] text-[var(--color-ink2)] min-w-0">
                  <span className="block font-bold truncate">{cred.owner_name || '—'}</span>
                  <span className="block text-[11px] text-[var(--color-ink3)] truncate">{cred.owner_email}</span>
                </span>
                <span className="col-span-2 text-[13px] text-[var(--color-ink2)]">
                  {cred.owner_department || '—'}
                </span>
                <span
                  className="col-span-2 font-mono text-[12px] text-[var(--color-ink3)]"
                  title={cred.scopes.join('\n')}
                >
                  {cred.scopes.length}개
                </span>
                <span className="col-span-2 text-[12px] flex items-center gap-1.5">
                  {cred.is_active ? (
                    <span className="inline-flex items-center gap-1 font-bold text-[var(--color-ink)]">
                      <Icon name="check" className="w-3.5 h-3.5" />
                      활성
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 font-bold text-[var(--color-danger)]">
                      <Icon name="x" className="w-3.5 h-3.5" />
                      해지
                    </span>
                  )}
                  <span className="text-[var(--color-ink3)]">· {formatDate(cred.connected_at)}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
