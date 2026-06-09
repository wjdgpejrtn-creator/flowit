'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Icon from '@/components/common/Icon';
import { showToast } from '@/stores/toastStore';
import { useAuthStore } from '@/stores/authStore';
import { useAuth } from '@/hooks/useAuth';
import {
  getConnections,
  getAvailableConnections,
  startConnection,
  revokeConnection,
  type ConnectionStatus,
  type AvailableConnection,
  type ConnectionAuthType,
} from '@/lib/api/connectionApi';

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
  const { userName, userId, email, dept, role } = useAuthStore();
  const [personalId, setPersonalId] = useState(userId || userName || email?.split('@')[0] || '사용자');
  const [displayName, setDisplayName] = useState(userName || email?.split('@')[0] || '');

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
  authType,
  available,
  connected,
  busy,
  onConnect,
  onRevoke,
  onManageKey,
}: {
  icon: string;
  iconBg: string;
  name: string;
  detail: string;
  authType: ConnectionAuthType;
  available: boolean;
  connected: boolean;
  busy: boolean;
  onConnect: () => void;
  onRevoke: () => void;
  onManageKey: () => void;
}) {
  // 연결 모델별 우측 액션 분기:
  //   oauth + 연결됨        → 연결됨 배지 + 해제
  //   oauth + 가능          → 연결(동의화면 이동)
  //   oauth + 미배선        → 준비 중(비활성)
  //   api_key/connection_string → 키 관리(자격증명 페이지)
  const renderAction = () => {
    if (authType === 'oauth') {
      if (connected) {
        return (
          <div className="flex items-center gap-2">
            <span
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold"
              style={{ background: '#E7F6EF', color: '#10B981' }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#10B981' }} />
              연결됨
            </span>
            <button
              type="button"
              onClick={onRevoke}
              disabled={busy}
              className="px-3 py-1.5 rounded-lg border border-line-soft text-ink3 text-[10px] font-bold hover:bg-paper/60 hover:text-danger disabled:opacity-50"
            >
              {busy ? '처리 중…' : '해제'}
            </button>
          </div>
        );
      }
      if (!available) {
        return (
          <button
            type="button"
            disabled
            className="px-3 py-1.5 rounded-lg border border-line-soft text-ink3 text-[10px] font-bold opacity-50 cursor-not-allowed"
          >
            준비 중
          </button>
        );
      }
      return (
        <button
          type="button"
          onClick={onConnect}
          disabled={busy}
          className="px-3 py-1.5 rounded-lg bg-accent text-white text-[10px] font-bold shadow-sm hover:bg-accent3 disabled:opacity-50"
        >
          {busy ? '연결 중…' : '연결'}
        </button>
      );
    }
    // api_key / connection_string — 자격증명 페이지에서 키 입력으로 연동.
    return (
      <button
        type="button"
        onClick={onManageKey}
        className="px-3 py-1.5 rounded-lg border border-line-soft text-ink text-[10px] font-bold hover:bg-paper/60"
      >
        키 관리
      </button>
    );
  };

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
      {renderAction()}
    </div>
  );
}

// 연결 가능 목록(이름·auth_type)은 GET /connections/available에서 도출. 아이콘·색만 프론트 표시 메타로
// 보유하고, 미정 service는 기본 아이콘으로 폴백(백엔드가 새 provider를 추가해도 깨지지 않게).
const SERVICE_STYLE: Record<string, { icon: string; iconBg: string }> = {
  slack: { icon: 'message-square', iconBg: '#4A154B' },
  google: { icon: 'sheet', iconBg: '#0F9D58' },
  linear: { icon: 'check-square', iconBg: '#5E6AD2' },
  anthropic: { icon: 'cpu', iconBg: '#D97757' },
  postgresql: { icon: 'database', iconBg: '#336791' },
  mysql: { icon: 'database', iconBg: '#00758F' },
};
const DEFAULT_STYLE = { icon: 'plug', iconBg: '#A2917F' };
const styleOf = (service: string) => SERVICE_STYLE[service] ?? DEFAULT_STYLE;

// 연결 모델별 비연결 상태 설명.
const detailForAuthType = (authType: ConnectionAuthType): string =>
  authType === 'api_key'
    ? 'API 키로 연동 — 자격증명에서 관리'
    : authType === 'connection_string'
      ? '접속 정보로 연동 — 자격증명에서 관리'
      : '연결되지 않음';

// callback 복귀 시그널(?connected / ?error)을 토스트로 표시하고 URL에서 정리한다.
// 백엔드 callback이 /settings?connected={service} 또는 ?error=connect_failed 로 리다이렉트한다.
function consumeConnectCallback(serviceLabel: (s: string) => string): void {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams(window.location.search);
  const connected = params.get('connected');
  const error = params.get('error');
  if (!connected && !error) return;

  if (connected) showToast(`${serviceLabel(connected)} 연결이 완료되었습니다.`);
  else if (error === 'connect_failed') showToast('연결에 실패했습니다. 다시 시도해주세요.');

  // 새로고침/뒤로가기 시 토스트 재발생 방지 — 쿼리만 제거.
  window.history.replaceState({}, '', window.location.pathname);
}

function IntegrationPanel() {
  const router = useRouter();
  const [available, setAvailable] = useState<AvailableConnection[]>([]);
  const [connections, setConnections] = useState<ConnectionStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busyServices, setBusyServices] = useState<Set<string>>(new Set());

  // 서비스별 처리 중 상태를 독립적으로 토글 — 여러 서비스 동시 연결/해제 시 각자 busy 표시.
  const setBusy = (service: string, busy: boolean) =>
    setBusyServices((prev) => {
      const next = new Set(prev);
      if (busy) next.add(service);
      else next.delete(service);
      return next;
    });

  // 연결 가능 목록(카탈로그 도출) + 현재 연결 상태를 함께 로드. 로드된 available를 반환해
  // 콜백 토스트가 친근명(예: "Google Workspace")으로 표시되게 한다.
  const load = async (): Promise<AvailableConnection[]> => {
    try {
      const [avail, conns] = await Promise.all([getAvailableConnections(), getConnections()]);
      setAvailable(avail);
      setConnections(conns);
      setError(false);
      return avail;
    } catch {
      setError(true);
      return [];
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // 로드 완료 후 콜백 토스트 표시 — available에서 service→표시명 매핑(미발견 시 키 폴백).
    void load().then((avail) => {
      consumeConnectCallback((svc) => avail.find((a) => a.service === svc)?.name ?? svc);
    });
  }, []);

  const handleConnect = async (service: string) => {
    setBusy(service, true);
    try {
      // 성공 시 OAuth 동의 화면으로 전체 페이지 이동(반환 없음).
      await startConnection(service);
    } catch {
      showToast('연결을 시작하지 못했습니다. 잠시 후 다시 시도해주세요.');
      setBusy(service, false);
    }
  };

  const handleRevoke = async (service: string) => {
    setBusy(service, true);
    try {
      await revokeConnection(service);
      showToast('연결을 해제했습니다.');
      await load();
    } catch {
      showToast('연결 해제에 실패했습니다. 다시 시도해주세요.');
    } finally {
      setBusy(service, false);
    }
  };

  const byService = new Map(connections.map((c) => [c.service, c]));

  return (
    <div className="space-y-5">
      <div className="border-b border-line-soft pb-2">
        <h3 className="text-sm font-bold text-ink">통합 연동</h3>
        <p className="text-[11px] text-ink3 font-bold">워크플로우에서 사용할 외부 서비스 계정을 연결하고 관리합니다.</p>
      </div>
      {error && <p className="text-[11px] text-danger font-bold">연결 상태를 불러오지 못했습니다.</p>}
      {loading && <p className="text-[11px] text-ink3 font-bold">불러오는 중…</p>}
      <div className="space-y-2.5">
        {available.map((s) => {
          const style = styleOf(s.service);
          const conn = byService.get(s.service);
          const connected = conn?.connected ?? false;
          const detail = connected
            ? conn?.display || '연결됨'
            : detailForAuthType(s.auth_type);
          return (
            <IntegrationRow
              key={s.service}
              icon={style.icon}
              iconBg={style.iconBg}
              name={s.name}
              detail={detail}
              authType={s.auth_type}
              available={s.available}
              connected={connected}
              busy={busyServices.has(s.service)}
              onConnect={() => void handleConnect(s.service)}
              onRevoke={() => void handleRevoke(s.service)}
              onManageKey={() => router.push('/admin/credentials')}
            />
          );
        })}
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
    // 시안: 0.9초 후 로그인 이동 + 최종 토스트(전체 이동 후 로그인 페이지에서 표시)
    setTimeout(() => void logout('모든 세션이 종료되어 로그아웃되었습니다.'), 900);
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
