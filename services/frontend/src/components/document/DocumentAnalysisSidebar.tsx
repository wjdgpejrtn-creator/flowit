'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Btn from '@/components/common/Btn';

// 디자인 SSOT: screens-3.jsx DocumentsScreen "통합" v2 우측 분석 사이드바.
// 분석/품질/PII 탭 → 📑 요약 → 🏷 키워드 → 👤 엔티티 → 🛠 Skills Builder.
//
// NOTE: 요약/키워드/엔티티는 분석 결과(AnalysisResult) 데이터인데, 이를 내려주는
// 프론트 API 엔드포인트가 아직 없어 placeholder 로 둔다. 백엔드 연동 후 props 로 주입.
// Skills Builder 핸드오프("이 문서로 스킬 만들기" / "SkillNode 후보 보기")는 REQ-010 에서
// 활성화 — /skills/builder?source_document_id=<id> 로 이동. 단 문서↔스킬 DB 연결
// (source_document_id 영속화)은 박아름 skills_marketplace 백엔드 wiring 후속.

type Tab = 'analysis' | 'quality' | 'pii';

const TABS: { key: Tab; label: string }[] = [
  { key: 'analysis', label: '분석' },
  { key: 'quality', label: '품질' },
  { key: 'pii', label: 'PII' },
];

function Placeholder({ text }: { text: string }) {
  return <div className="text-[12px] text-[var(--color-ink4)] mt-2">{text}</div>;
}

export default function DocumentAnalysisSidebar({
  analyzed,
  documentId,
}: {
  analyzed: boolean;
  documentId: string;
}) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>('analysis');

  return (
    <div className="border-l-[1.5px] border-[var(--color-ink)] bg-[var(--color-paper2)] p-[10px] overflow-auto">
      {/* 탭 */}
      <div className="flex items-center gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={[
              'text-[12px] px-2 py-[2px] rounded-full border-[1.5px] cursor-pointer transition-colors',
              tab === t.key
                ? 'bg-[var(--color-ink)] text-[var(--color-surface)] border-[var(--color-ink)]'
                : 'bg-transparent text-[var(--color-ink3)] border-[var(--color-line-soft)] hover:border-[var(--color-ink)]',
            ].join(' ')}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'analysis' && (
        <>
          <div className="font-bold text-[13px] mt-3">📑 요약</div>
          {analyzed ? (
            <Placeholder text="요약 데이터는 분석 결과 API 연동 후 표시됩니다." />
          ) : (
            <Placeholder text="문서를 분석하면 요약이 표시됩니다." />
          )}

          <div className="font-bold text-[13px] mt-3">🏷 키워드</div>
          {analyzed ? (
            <Placeholder text="키워드 데이터는 분석 결과 API 연동 후 표시됩니다." />
          ) : (
            <Placeholder text="문서를 분석하면 키워드가 표시됩니다." />
          )}

          <div className="font-bold text-[13px] mt-3">👤 엔티티</div>
          {analyzed ? (
            <Placeholder text="엔티티 데이터는 분석 결과 API 연동 후 표시됩니다." />
          ) : (
            <Placeholder text="문서를 분석하면 엔티티가 표시됩니다." />
          )}
        </>
      )}

      {tab === 'quality' && <Placeholder text="품질 게이트 결과는 분석 결과 API 연동 후 표시됩니다." />}
      {tab === 'pii' && <Placeholder text="PII 마스킹 내역은 분석 결과 API 연동 후 표시됩니다." />}

      {/* 구분선 */}
      <div className="h-[1px] bg-[var(--color-line-soft)] my-3" />

      {/* Skills Builder 핸드오프 — 이 문서를 기반 문서로 지정해 빌더로 이동(빈 폼).
          문서에서 노드 후보를 자동 추출하는 기능은 Skills Builder Agent(REQ-004 ③,
          정혜님/박아름) 연동이 필요해 아직 없음 — 라벨을 실제 동작에 맞춤. */}
      <div className="font-bold text-[13px]">🛠 Skills Builder</div>
      <div className="text-[11px] text-[var(--color-ink4)] mt-2">
        이 문서를 기반으로 새 스킬을 만들 수 있어요.
      </div>
      <Btn
        primary
        title="이 문서를 기반으로 새 스킬 만들기"
        onClick={() => router.push(`/skills/builder?source_document_id=${documentId}`)}
        className="mt-2 w-full justify-center"
      >
        이 문서로 스킬 만들기 →
      </Btn>
    </div>
  );
}
