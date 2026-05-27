'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import Skel from '@/components/common/Skel';
import ErrorBanner from '@/components/common/ErrorBanner';
import {
  getPersonalSkill,
  updatePersonalSkill,
  deletePersonalSkill,
  type PersonalSkill,
  type SkillLifecycleState,
} from '@/lib/api/skillApi';

/* ── Lifecycle pill (marketplace와 동일) ── */

const LIFECYCLE_CONFIG: Record<SkillLifecycleState, { color: string; label: string }> = {
  draft:     { color: 'var(--color-ink4)',     label: '초안' },
  review:    { color: 'var(--color-risk-med)',  label: '검토 중' },
  approved:  { color: 'var(--color-risk-low)',  label: '승인됨' },
  published: { color: 'var(--color-accent)',    label: '게시됨' },
};

function LifecyclePill({ state }: { state: SkillLifecycleState }) {
  const { color, label } = LIFECYCLE_CONFIG[state];
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-[1px] rounded border-[1.5px] whitespace-nowrap"
      style={{ borderColor: color, color }}
    >
      <span className="w-[6px] h-[6px] rounded-full flex-shrink-0" style={{ background: color }} />
      {label}
    </span>
  );
}

/* ── 에러 메시지 분류 ── */

function toErrorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : '';
  if (msg.startsWith('401')) return '로그인이 만료되었습니다.';
  if (msg.startsWith('403')) return '이 스킬에 접근할 권한이 없습니다.';
  if (msg.startsWith('404')) return '스킬을 찾을 수 없습니다.';
  if (msg.startsWith('5')) return '서버 오류가 발생했습니다.';
  if (msg === 'Failed to fetch' || msg === 'Load failed') return '네트워크 연결을 확인해 주세요.';
  return '스킬 정보를 불러올 수 없습니다.';
}

/* ── 읽기 전용 필드 행 ── */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-[6px] border-b border-[var(--color-line-soft)]">
      <span className="text-[12px] text-[var(--color-ink3)] w-[100px] flex-shrink-0 pt-[2px]">{label}</span>
      <span className="text-[13px] text-[var(--color-ink)] flex-1">{children}</span>
    </div>
  );
}

/* ── 메인 페이지 ── */

export default function SkillDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [skill, setSkill] = useState<PersonalSkill | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 편집 상태
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editTags, setEditTags] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // 삭제 상태
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fetchSkill = useCallback(() => {
    setLoading(true);
    setError(null);
    getPersonalSkill(id)
      .then((s) => {
        setSkill(s);
        setEditName(s.name);
        setEditDesc(s.description);
        setEditTags(s.tags.join(', '));
      })
      .catch((err) => setError(toErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    fetchSkill();
  }, [fetchSkill]);

  const isDraft = skill?.lifecycle_state === 'draft';

  const handleStartEdit = () => {
    if (!skill) return;
    setEditName(skill.name);
    setEditDesc(skill.description);
    setEditTags(skill.tags.join(', '));
    setSaveError(null);
    setEditing(true);
  };

  const handleCancelEdit = () => {
    setEditing(false);
    setSaveError(null);
  };

  const handleSave = async () => {
    if (!skill) return;
    setSaving(true);
    setSaveError(null);
    try {
      const tags = editTags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);
      const updated = await updatePersonalSkill(skill.skill_id, {
        name: editName,
        description: editDesc,
        tags,
      });
      setSkill(updated);
      setEditing(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      if (msg.startsWith('400')) setSaveError('DRAFT 상태의 스킬만 수정할 수 있습니다.');
      else setSaveError('저장에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!skill) return;
    setDeleting(true);
    try {
      await deletePersonalSkill(skill.skill_id);
      router.push('/marketplace?tab=personal');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      if (msg.startsWith('400')) setSaveError('DRAFT 상태의 스킬만 삭제할 수 있습니다.');
      else setSaveError('삭제에 실패했습니다. 다시 시도해 주세요.');
      setConfirmDelete(false);
      setDeleting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      {/* Header bar */}
      <div className="flex items-center gap-[10px] px-3 py-2 border-b-[1.5px] border-[var(--color-ink)] bg-[var(--color-surface)]">
        <Link
          href="/marketplace?tab=personal"
          className="text-[13px] text-[var(--color-ink3)] hover:text-[var(--color-ink)] no-underline"
        >
          &larr; 스킬 목록
        </Link>
        <span className="text-[var(--color-ink4)]">|</span>
        {loading ? (
          <Skel className="w-40 h-4" />
        ) : skill ? (
          <>
            <span className="font-bold text-[14px]">{skill.name}</span>
            <LifecyclePill state={skill.lifecycle_state} />
          </>
        ) : null}
      </div>

      {/* Error */}
      {error && (
        <div className="px-3 pt-3">
          <ErrorBanner>
            <span>{error}</span>
          </ErrorBanner>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="p-[14px] flex flex-col gap-3 max-w-[640px]">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skel key={i} className="h-[28px] w-full" />
          ))}
        </div>
      )}

      {/* Content */}
      {!loading && !error && skill && (
        <div className="p-[14px] flex flex-col gap-3 max-w-[640px]">
          {/* Save error */}
          {saveError && (
            <ErrorBanner small>
              <span>{saveError}</span>
            </ErrorBanner>
          )}

          <div className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] p-[14px] flex flex-col">
            {editing ? (
              /* ── 편집 폼 ── */
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-[12px] text-[var(--color-ink3)]">이름</label>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="border-[1.5px] border-[var(--color-ink)] rounded px-2 py-[4px] text-[13px] bg-[var(--color-paper)] outline-none focus:border-[var(--color-accent)]"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[12px] text-[var(--color-ink3)]">설명</label>
                  <textarea
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                    rows={4}
                    className="border-[1.5px] border-[var(--color-ink)] rounded px-2 py-[4px] text-[13px] bg-[var(--color-paper)] outline-none focus:border-[var(--color-accent)] resize-y"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[12px] text-[var(--color-ink3)]">태그 (쉼표 구분)</label>
                  <input
                    type="text"
                    value={editTags}
                    onChange={(e) => setEditTags(e.target.value)}
                    placeholder="예: 리포트, AI, 자동화"
                    className="border-[1.5px] border-[var(--color-ink)] rounded px-2 py-[4px] text-[13px] bg-[var(--color-paper)] outline-none focus:border-[var(--color-accent)]"
                  />
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <Btn primary onClick={handleSave} disabled={saving}>
                    {saving ? '저장 중…' : '저장'}
                  </Btn>
                  <Btn ghost onClick={handleCancelEdit} disabled={saving}>
                    취소
                  </Btn>
                </div>
              </div>
            ) : (
              /* ── 읽기 모드 ── */
              <div className="flex flex-col">
                <Field label="이름">{skill.name}</Field>
                <Field label="설명">
                  <span className="whitespace-pre-wrap">{skill.description || '-'}</span>
                </Field>
                <Field label="태그">
                  {skill.tags.length > 0 ? (
                    <span className="flex flex-wrap gap-1">
                      {skill.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[11px] border border-[var(--color-ink4)] rounded px-[6px] py-0 text-[var(--color-ink3)]"
                        >
                          {tag}
                        </span>
                      ))}
                    </span>
                  ) : (
                    '-'
                  )}
                </Field>
                <Field label="상태">
                  <LifecyclePill state={skill.lifecycle_state} />
                </Field>
                <Field label="버전">v{skill.version}</Field>
                <Field label="생성일">{new Date(skill.created_at).toLocaleString('ko-KR')}</Field>
                <Field label="수정일">{new Date(skill.updated_at).toLocaleString('ko-KR')}</Field>
                {skill.workflow_id && <Field label="워크플로우 ID">{skill.workflow_id}</Field>}
                {skill.node_definition_id && <Field label="노드 ID">{skill.node_definition_id}</Field>}

                {/* 액션 버튼 — DRAFT만 */}
                {isDraft && (
                  <div className="flex items-center gap-2 pt-3">
                    <Btn primary onClick={handleStartEdit}>수정</Btn>
                    {confirmDelete ? (
                      <>
                        <Btn danger onClick={handleDelete} disabled={deleting}>
                          {deleting ? '삭제 중…' : '정말 삭제'}
                        </Btn>
                        <Btn ghost onClick={() => setConfirmDelete(false)} disabled={deleting}>
                          취소
                        </Btn>
                      </>
                    ) : (
                      <Btn danger onClick={() => setConfirmDelete(true)}>삭제</Btn>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
