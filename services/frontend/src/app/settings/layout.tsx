import AppBar from '@/components/common/AppBar';

// 설정은 단일 페이지(좌측 패널 내부 전환, 시안 SSOT)로 재설계됨.
// 레이아웃은 공통 헤더(AppBar)만 제공하고, 화면 구성은 각 페이지가 담당한다.
export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <AppBar />
      {children}
    </div>
  );
}
