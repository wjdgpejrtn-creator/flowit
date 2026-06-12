'use client';

import { useEffect, useRef } from 'react';
import AppBar from '@/components/common/AppBar';
import SkillBuilderWizard from '@/components/skill/SkillBuilderWizard';
import { useSkillBuilderStore } from '@/stores/skillBuilderStore';

/**
 * 스킬빌더 페이지 — 위저드 로직은 skillBuilderStore + components/skill/* 로 이관됐고,
 * 이 페이지는 (a) 셸(AppBar/레이아웃)과 (b) URL 핸드오프(문서→빌더 ?source_document_id=,
 * 마켓 수정 ?edit=1)만 담당한다. 같은 위저드를 문서 탭/AI 채팅에서도 재사용한다.
 *
 * nav 탭에서는 제거됐고(문서 탭/채팅으로 통합), 이 route는 마켓 '수정'·deep-link 진입용으로
 * 존치한다.
 */
export default function SkillBuilderPage() {
  // 첫 진입 1회: 문서→빌더 핸드오프(?source_document_id=) 또는 마켓 수정(?edit=1).
  const initHandled = useRef(false);
  useEffect(() => {
    if (initHandled.current) return;
    initHandled.current = true;

    const sp = new URLSearchParams(window.location.search);
    const store = useSkillBuilderStore.getState();
    // 싱글톤 store — 직전 방문 잔재를 비우고 시작(이전 page-local useState와 동일하게 fresh).
    store.reset();

    const src = sp.get('source_document_id');
    if (src) {
      store.setBranch('document');
      store.startBuild({ kind: 'document', id: src, label: src });
      return;
    }
    if (sp.get('edit') === '1') {
      store.initEdit({
        name: sp.get('name') ?? '',
        description: sp.get('desc') ?? '',
        tags: sp.get('tags') ?? '',
      });
    }
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <AppBar />
      <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-4">
        <SkillBuilderWizard />
      </main>
    </div>
  );
}
