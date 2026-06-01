'use client';

import { useState } from 'react';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import { useAuthStore } from '@/stores/authStore';
import { useAuth } from '@/hooks/useAuth';

type Panel = 'profile' | 'integration' | 'alert' | 'security';

const PANELS: { key: Panel; label: string }[] = [
  { key: 'profile', label: '프로필' },
  { key: 'integration', label: '통합' },
  { key: 'alert', label: '알림' },
  { key: 'security', label: '보안' },
];

function NavBtn({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'w-full text-left px-4 py-2.5 rounded-xl text-xs font-bold transition-all',
        active ? 'bg-accent text-white' : 'text-ink3 hover:text-ink hover:bg-white',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

function ProfilePanel() {
  const { userName, userId, dept, role } = useAuthStore();
  const [personalId, setPersonalId] = useState(userId || userName || 'gawon.data');
  const [displayName, setDisplayName] = useState(userName || '');

  const save = () => {
    if (!personalId.trim()) {
      showToast('개인 ID를 입력해주세요.');
      return;
    }
    showToast(`프로필이 저장되었습니다${displayName ? ` (${displayName}님)` : ''}.`);
  };

  return (
    <div className="space-y-5">
      <div className="border-b border-line-soft pb-2">
        <h3 className="text-sm font-bold text-ink">프로필</h3>
        <p className="text-[11px] text-ink3 font-bold">사내 노드원 이름, 부서, 역할 정보를 확인 및 관리합니다.</p>
      </div>

      <div className="space-y-1">
        <label className="text-[10px] uppercase text-ink3 tracking-widest font-bold">개인 ID</label>
        <div className="flex items-center justify-between p-2.5 rounded-xl border border-line-soft bg-white focus-within:border-accent transition-all">
          <input
            value={personalId}
            onChange={(e) => setPersonalId(e.target.value)}
            aria-label="개인 ID"
            className="text-xs font-bold text-ink bg-transparent focus:outline-none flex-1 mr-2"
          />
          <span className="text-[10px] font-bold flex-shrink-0" style={{ color: '#10B981' }}>
            수정 가능
          </span>
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-[10px] uppercase text-ink3 tracking-widest font-bold">표시 이름</label>
        <div className="p-2.5 rounded-xl border border-line-soft bg-white focus-within:border-accent transition-all">
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="이름을 입력하세요"
            aria-label="표시 이름"
            className="w-full text-xs font-bold text-ink bg-transparent focus:outline-none"
          />
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-[10px] uppercase text-ink3 tracking-widest font-bold">
          부서 <span className="text-ink4 normal-case tracking-normal">· 시스템 관리</span>
        </label>
        <div className="flex items-center justify-between p-2.5 rounded-xl border border-line-soft bg-paper/40">
          <span className="text-xs font-bold text-ink4">{dept || '—'}</span>
          <Icon name="lock" className="w-3.5 h-3.5 text-ink4" />
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-[10px] uppercase text-ink3 tracking-widest font-bold">
          역할 <span className="text-ink4 normal-case tracking-normal">· 관리자 지정</span>
        </label>
        <div className="flex items-center justify-between p-2.5 rounded-xl border border-line-soft bg-paper/40">
          <span className="text-xs font-bold text-ink4">{role}</span>
          <Icon name="lock" className="w-3.5 h-3.5 text-ink4" />
        </div>
      </div>

      <button
        type="button"
        onClick={save}
        className="px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3"
      >
        프로필 저장
      </button>
    </div>
  );
}

function IntegrationRow({
  icon,
  iconBg,
  name,
  detail,
  connected,
}: {
  icon: string;
  iconBg: string;
  name: string;
  detail: string;
  connected: boolean;
}) {
  return (
    <div className="flex items-center justify-between p-3.5 rounded-xl border border-line-soft bg-white">
      <div className="flex items-center space-x-3">
        <span
          className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: iconBg }}
        >
          <Icon name={icon} className="w-4 h-4 text-white" />
        </span>
        <div>
          <p className="text-xs font-bold text-ink">{name}</p>
          <p className="text-[10px] text-ink3 font-bold">{detail}</p>
        </div>
      </div>
      {connected ? (
        <span
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold"
          style={{ background: '#E7F6EF', color: '#10B981' }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#10B981' }} />
          연결됨
        </span>
      ) : (
        <button
          type="button"
          onClick={() => showToast('ERP 연동을 시작합니다.')}
          className="px-3 py-1.5 rounded-lg bg-accent text-white text-[10px] font-bold shadow-sm hover:bg-accent3"
        >
          연결
        </button>
      )}
    </div>
  );
}

function IntegrationPanel() {
  return (
    <div className="space-y-5">
      <div className="border-b border-line-soft pb-2">
        <h3 className="text-sm font-bold text-ink">통합 연동</h3>
        <p className="text-[11px] text-ink3 font-bold">워크플로우에서 사용할 외부 서비스 계정을 연결하고 관리합니다.</p>
      </div>
      <div className="space-y-2.5">
        <IntegrationRow icon="message-square" iconBg="#4A154B" name="Slack" detail="workspace · flowit-team" connected />
        <IntegrationRow icon="sheet" iconBg="#0F9D58" name="Google Workspace" detail="gawon.data@flowit.io" connected />
        <IntegrationRow icon="database" iconBg="#A2917F" name="사내 ERP" detail="연결되지 않음" connected={false} />
      </div>
      <button
        type="button"
        onClick={() => showToast('통합 설정이 저장되었습니다.')}
        className="px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3"
      >
        설정 저장
      </button>
    </div>
  );
}

const ALERTS: { title: string; desc: string; on: boolean }[] = [
  { title: '워크플로우 완료 알림', desc: '자동화 실행이 끝나면 알려드립니다.', on: true },
  { title: '오류 발생 알림', desc: '노드 실행 실패 시 즉시 알림을 받습니다.', on: true },
  { title: '주간 요약 리포트', desc: '매주 월요일 자동화 통계를 메일로 받습니다.', on: false },
  { title: '마켓플레이스 신규 스킬', desc: '전사 추천 스킬이 등록되면 알려드립니다.', on: false },
];

function AlertPanel() {
  return (
    <div className="space-y-5">
      <div className="border-b border-line-soft pb-2">
        <h3 className="text-sm font-bold text-ink">알림</h3>
        <p className="text-[11px] text-ink3 font-bold">워크플로우 실행 및 시스템 이벤트 알림 수신 방식을 설정합니다.</p>
      </div>
      {ALERTS.map((a) => (
        <label
          key={a.title}
          className="flex items-center justify-between p-3.5 rounded-xl border border-line-soft bg-white cursor-pointer"
        >
          <div>
            <p className="text-xs font-bold text-ink">{a.title}</p>
            <p className="text-[10px] text-ink3 font-bold">{a.desc}</p>
          </div>
          <input type="checkbox" defaultChecked={a.on} className="settings-toggle" />
        </label>
      ))}
      <button
        type="button"
        onClick={() => showToast('알림 설정이 저장되었습니다.')}
        className="px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3"
      >
        알림 설정 저장
      </button>
    </div>
  );
}

function SecurityPanel() {
  const { logout } = useAuth();
  const [pwOpen, setPwOpen] = useState(false);
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');

  const togglePwChange = () => {
    if (!pwOpen) {
      setPwOpen(true);
      return;
    }
    if (!cur || !next || !confirm) {
      showToast('비밀번호 필드를 모두 입력해주세요.');
      return;
    }
    if (next !== confirm) {
      showToast('새 비밀번호가 일치하지 않습니다.');
      return;
    }
    setPwOpen(false);
    setCur('');
    setNext('');
    setConfirm('');
    showToast('비밀번호가 변경되었습니다.');
  };

  const logoutAll = () => {
    showToast('모든 기기에서 로그아웃합니다...');
    setTimeout(() => void logout(), 700);
  };

  return (
    <div className="space-y-5">
      <div className="border-b border-line-soft pb-2">
        <h3 className="text-sm font-bold text-ink">보안</h3>
        <p className="text-[11px] text-ink3 font-bold">계정 인증 및 접근 보안 정책을 관리합니다.</p>
      </div>

      <div className="flex items-center justify-between p-3.5 rounded-xl border border-line-soft bg-white">
        <div>
          <p className="text-xs font-bold text-ink">2단계 인증 (2FA)</p>
          <p className="text-[10px] text-ink3 font-bold">로그인 시 추가 인증을 요구합니다.</p>
        </div>
        <span
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold"
          style={{ background: '#E7F6EF', color: '#10B981' }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#10B981' }} />
          활성
        </span>
      </div>

      <div className="space-y-1">
        <label className="text-[10px] uppercase text-ink3 tracking-widest font-bold">세션 인증 쿠키</label>
        <div className="flex items-center justify-between p-2.5 rounded-xl border border-line-soft bg-paper/40">
          <span className="text-xs font-mono text-ink4">HttpOnly · Secure · SameSite=Strict</span>
          <Icon name="lock" className="w-3.5 h-3.5 text-ink3" />
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-[10px] uppercase text-ink3 tracking-widest font-bold">최근 로그인</label>
        <div className="p-2.5 rounded-xl border border-line-soft bg-paper/40">
          <span className="text-xs font-bold text-ink4">2026-05-31 09:12 · Seoul, KR · Chrome</span>
        </div>
      </div>

      {pwOpen && (
        <div className="space-y-2 p-3.5 rounded-xl border border-line-soft bg-paper/30">
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-ink3 tracking-widest font-bold">현재 비밀번호</label>
            <input
              type="password"
              value={cur}
              onChange={(e) => setCur(e.target.value)}
              placeholder="현재 비밀번호"
              className="w-full p-2.5 rounded-xl border border-line-soft focus:outline-none focus:border-accent bg-white text-xs font-bold text-ink"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-ink3 tracking-widest font-bold">새 비밀번호</label>
            <input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              placeholder="새 비밀번호 (8자 이상)"
              className="w-full p-2.5 rounded-xl border border-line-soft focus:outline-none focus:border-accent bg-white text-xs font-bold text-ink"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] uppercase text-ink3 tracking-widest font-bold">새 비밀번호 확인</label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="새 비밀번호 확인"
              className="w-full p-2.5 rounded-xl border border-line-soft focus:outline-none focus:border-accent bg-white text-xs font-bold text-ink"
            />
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={togglePwChange}
          className="px-5 py-2.5 rounded-xl bg-accent text-white text-xs font-bold shadow-sm hover:bg-accent3"
        >
          {pwOpen ? '변경 사항 저장' : '비밀번호 변경'}
        </button>
        <button
          type="button"
          onClick={logoutAll}
          className="px-5 py-2.5 rounded-xl border border-danger/30 text-danger text-xs font-bold hover:bg-danger-soft transition-all"
        >
          모든 기기 로그아웃
        </button>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const [panel, setPanel] = useState<Panel>('profile');

  return (
    <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 space-y-4">
      <div>
        <h2 className="text-lg font-bold text-ink">설정</h2>
        <p className="text-xs text-ink3 font-bold">플로잇 시스템 환경 및 보안, 통합 연동 설정을 제어합니다.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-3 bg-paper2/40 rounded-2xl p-3 space-y-1 h-fit">
          {PANELS.map((p) => (
            <NavBtn key={p.key} active={panel === p.key} label={p.label} onClick={() => setPanel(p.key)} />
          ))}
        </div>

        <div className="lg:col-span-9 bg-white border border-line-soft rounded-2xl p-6 shadow-sm self-start">
          {panel === 'profile' && <ProfilePanel />}
          {panel === 'integration' && <IntegrationPanel />}
          {panel === 'alert' && <AlertPanel />}
          {panel === 'security' && <SecurityPanel />}
        </div>
      </div>
    </main>
  );
}
