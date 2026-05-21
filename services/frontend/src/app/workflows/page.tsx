import Link from 'next/link';
import AppBar from '@/components/common/AppBar';
import Btn from '@/components/common/Btn';
import RiskPill from '@/components/common/RiskPill';
import StatusPill from '@/components/common/StatusPill';
import ScopePill from '@/components/common/ScopePill';
import Skel from '@/components/common/Skel';
import { RiskLevel, ExecutionStatus } from '@common/generated';

type WorkflowItem = {
  id: string;
  name: string;
  status: `${ExecutionStatus}`;
  risk: RiskLevel;
  scope: 'private' | 'team' | 'public';
  nodes: number;
  when: string;
};

const ITEMS: WorkflowItem[] = [
  { id: '1', name: '주간 회의록 요약',  status: ExecutionStatus.COMPLETED, risk: RiskLevel.HIGH,       scope: 'private', nodes: 4, when: '3시간 전' },
  { id: '2', name: '견적 PDF 분류',    status: ExecutionStatus.RUNNING,   risk: RiskLevel.MEDIUM,     scope: 'team',    nodes: 6, when: '진행 중' },
  { id: '3', name: 'CS 티켓 라우팅',   status: ExecutionStatus.FAILED,    risk: RiskLevel.RESTRICTED, scope: 'team',    nodes: 8, when: '12분 전' },
  { id: '4', name: 'OKR 주간 요약',    status: ExecutionStatus.COMPLETED, risk: RiskLevel.LOW,        scope: 'public',  nodes: 5, when: '어제' },
  { id: '5', name: '예산 알림 봇',     status: ExecutionStatus.PAUSED,    risk: RiskLevel.MEDIUM,     scope: 'team',    nodes: 3, when: '2일 전' },
  { id: '6', name: '뉴스 클리핑',      status: ExecutionStatus.COMPLETED, risk: RiskLevel.LOW,        scope: 'public',  nodes: 7, when: '3일 전' },
];

const TABLE_HEAD = ['이름', 'SCOPE', '위험도', '노드', '마지막 실행', '수정'];

export default function WorkflowListPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <AppBar />

      <div className="flex-1 flex flex-col gap-[10px] p-[14px]">
        {/* Toolbar */}
        <div className="flex items-center justify-between">
          {/* Tabs */}
          <div className="flex gap-2">
            {[['My', 6], ['Team', 23], ['Public', 117]].map(([label, count]) => (
              <button
                key={label}
                className={[
                  'text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-2 py-[3px]',
                  label === 'My'
                    ? 'bg-[var(--color-ink)] text-[var(--color-paper)]'
                    : 'bg-[var(--color-surface)] text-[var(--color-ink)] hover:bg-[var(--color-paper2)]',
                ].join(' ')}
              >
                {label} <span className="font-mono text-[11px] opacity-70">{count}</span>
              </button>
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <div
              className="text-[13px] border-[1.5px] border-[var(--color-ink)] rounded-[4px_8px_4px_8px] px-[8px] py-[2px] bg-[var(--color-surface)] text-[var(--color-ink3)]"
            >
              🔍 검색…
            </div>
            <Btn primary>＋ 빈 캔버스</Btn>
            <Link href="/agent">
              <Btn>🤖 AI에게 요청</Btn>
            </Link>
          </div>
        </div>

        {/* Table */}
        <div
          className="border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] bg-[var(--color-surface)] overflow-hidden"
        >
          {/* Header */}
          <div
            className="flex items-center font-mono text-[11px] text-[var(--color-ink4)] px-[10px] py-[6px] border-b border-[var(--color-ink4)]"
            style={{ background: 'var(--color-paper2)' }}
          >
            <span style={{ flex: 2 }}>{TABLE_HEAD[0]}</span>
            <span style={{ flex: 1 }}>{TABLE_HEAD[1]}</span>
            <span style={{ flex: 0.7 }}>{TABLE_HEAD[2]}</span>
            <span style={{ flex: 0.7 }}>{TABLE_HEAD[3]}</span>
            <span style={{ flex: 1 }}>{TABLE_HEAD[4]}</span>
            <span style={{ flex: 1 }}>{TABLE_HEAD[5]}</span>
          </div>

          {/* Rows */}
          {ITEMS.map((item, i) => (
            <Link
              key={item.id}
              href={`/workflows/${item.id}`}
              className={[
                'flex items-center px-[10px] py-[8px] no-underline text-[var(--color-ink)] hover:bg-[var(--color-paper2)]',
                i < ITEMS.length - 1 ? 'border-b border-[var(--color-ink4)]' : '',
              ].join(' ')}
            >
              <span className="font-bold" style={{ flex: 2 }}>{item.name}</span>
              <span style={{ flex: 1 }}><ScopePill scope={item.scope} /></span>
              <span style={{ flex: 0.7 }}><RiskPill level={item.risk} /></span>
              <span className="font-mono text-[11px]" style={{ flex: 0.7 }}>{item.nodes}개</span>
              <span style={{ flex: 1 }}><StatusPill status={item.status} /></span>
              <span className="text-[13px] text-[var(--color-ink3)]" style={{ flex: 1 }}>{item.when}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
