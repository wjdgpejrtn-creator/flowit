import Btn from '@/components/common/Btn';

const INTEGRATIONS = [
  { name: 'Google Drive',  status: 'ok',   label: '12일 후 만료' },
  { name: 'Google Sheets', status: 'ok',   label: '12일 후 만료' },
  { name: 'Gmail',         status: 'ok',   label: '12일 후 만료' },
  { name: 'Slack',         status: 'warn', label: '7일 후 만료 ⚠' },
  { name: 'Calendar',      status: 'ok',   label: '연결됨' },
  { name: 'Notion',        status: 'off',  label: '연결 안됨' },
  { name: 'Outlook',       status: 'off',  label: '연결 안됨' },
  { name: 'Teams',         status: 'off',  label: '연결 안됨' },
];

export default function SettingsIntegrationsPage() {
  return (
    <>
      <div className="font-bold text-[16px] mb-[2px]">OAuth 통합</div>
      <div className="text-[13px] text-[var(--color-ink3)] mb-3">연결된 외부 서비스 · 토큰 만료 경고</div>

      <div className="flex flex-col gap-2">
        {INTEGRATIONS.map((it) => (
          <div
            key={it.name}
            className="flex items-center justify-between border-[1.5px] border-[var(--color-ink)] rounded-[5px_11px_6px_10px] px-[10px] py-[8px] bg-[var(--color-surface)]"
          >
            <span className="flex items-center gap-2">
              <span
                className="inline-flex items-center justify-center w-5 h-5 border-[1.5px] border-[var(--color-ink)] rounded font-mono text-[11px] bg-[var(--color-paper2)]"
              >
                {it.name[0]}
              </span>
              <span className="font-bold text-[13px]">{it.name}</span>
              <span
                className="text-[11px] px-[6px] py-0 border border-[var(--color-ink4)] rounded text-[var(--color-ink3)]"
                style={it.status === 'warn' ? { color: 'var(--color-risk-med)', borderColor: 'var(--color-risk-med)' } : {}}
              >
                {it.label}
              </span>
            </span>

            <span className="flex items-center gap-2">
              {it.status === 'off' ? (
                <Btn primary>연결</Btn>
              ) : (
                <>
                  <Btn ghost>토큰 갱신</Btn>
                  <Btn danger>해제</Btn>
                </>
              )}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}
