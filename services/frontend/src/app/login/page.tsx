import Btn from '@/components/common/Btn';
import ErrorBanner from '@/components/common/ErrorBanner';

export default function LoginPage() {
  return (
    <div className="min-h-screen flex bg-[var(--color-paper2)]">
      {/* Left: copy */}
      <div
        className="flex flex-col justify-center gap-[14px] p-10 border-r-[1.5px] border-[var(--color-ink3)]"
        style={{ flex: '1.1' }}
      >
        <div className="font-bold text-[22px] tracking-[-0.02em]">∿ flow</div>
        <div className="font-bold text-[18px] leading-[1.4] font-normal">
          자연어로 <span className="bg-[var(--color-hl)] px-1">업무 자동화</span>를<br />
          요청하세요.
        </div>
        <div className="text-[14px] text-[var(--color-ink3)] leading-[1.55]">
          AI 에이전트가 56종 노드로<br />
          워크플로우를 조립합니다.
        </div>
        <div className="font-mono text-[var(--color-ink4)] mt-[14px] text-[12px]">v1.0 · 베타</div>
      </div>

      {/* Right: login form */}
      <div
        className="flex flex-col justify-center gap-3 p-[30px_24px]"
        style={{ flex: '1' }}
      >
        <div className="text-[12px] text-[var(--color-ink3)] font-medium">로그인</div>
        <a href="/api/auth/google" className="no-underline">
          <Btn lg primary>🇬 Google로 로그인</Btn>
        </a>
        <div className="text-[13px] text-[var(--color-ink3)]">
          사내 도메인:{' '}
          <span className="font-mono text-[var(--color-ink)]">@naver.com</span>
        </div>

        {/* Error state — shown conditionally in real app */}
        {false && (
          <ErrorBanner>
            <span>⚠</span>
            <span>401 · 허용되지 않은 계정입니다. Admin에게 문의하세요.</span>
          </ErrorBanner>
        )}

        <div className="mt-[14px] h-[1.5px] bg-[var(--color-ink3)] rounded" />
        <div className="text-[11px] text-[var(--color-ink3)]">
          로그인 시 TokenPair (access+refresh)가 안전 저장됩니다.
        </div>
      </div>
    </div>
  );
}
