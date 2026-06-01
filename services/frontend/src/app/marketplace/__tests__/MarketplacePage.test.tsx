import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams('tab=personal'),
  usePathname: () => '/marketplace',
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));

jest.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({ role: 'User', userName: 'tester', dept: '', isAuthenticated: true }),
}));

jest.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

import MarketplacePage from '../page';
import { __resetMarketplaceMock } from '../../../lib/api/marketplaceMockApi';

beforeEach(() => {
  __resetMarketplaceMock();
});

describe('MarketplacePage — 재설계(Flowit)', () => {
  it('초기 로드 시 스켈레톤을 표시한다', () => {
    // listSkills resolve는 마이크로태스크 — 동기 시점엔 아직 loading=true
    render(<MarketplacePage />);
    expect(document.querySelectorAll('.animate-shimmer').length).toBeGreaterThan(0);
  });

  it('Personal 스킬 카드를 렌더링한다 (이름·상태 pill·버전)', async () => {
    render(<MarketplacePage />);
    await waitFor(() => {
      expect(screen.getByText('슬랙 통합 리포트 마스터')).toBeInTheDocument();
    });
    // draft 상태 pill
    expect(screen.getByText('초안')).toBeInTheDocument();
    // 헤더
    expect(screen.getByText('내가 만든 스킬')).toBeInTheDocument();
  });

  it('검색어로 필터링하고, 결과 없으면 안내를 표시한다', async () => {
    render(<MarketplacePage />);
    await waitFor(() => screen.getByText('슬랙 통합 리포트 마스터'));

    const search = screen.getByLabelText('스킬 검색');
    await userEvent.type(search, '문서');
    expect(screen.getByText('문서 자동 분류 봇')).toBeInTheDocument();
    expect(screen.queryByText('슬랙 통합 리포트 마스터')).not.toBeInTheDocument();

    await userEvent.clear(search);
    await userEvent.type(search, '존재하지않는스킬');
    await waitFor(() => {
      expect(screen.getByText("'존재하지않는스킬' 검색 결과가 없습니다.")).toBeInTheDocument();
    });
  });

  it('Team 탭으로 전환하면 팀 헤더와 스킬을 보여준다', async () => {
    render(<MarketplacePage />);
    await waitFor(() => screen.getByText('슬랙 통합 리포트 마스터'));

    await userEvent.click(screen.getByRole('button', { name: 'Team' }));
    await waitFor(() => {
      expect(screen.getByText('동료가 공유한 스킬')).toBeInTheDocument();
    });
    expect(screen.getByText('인사 정보 ERP 자동 기입봇')).toBeInTheDocument();
  });

  it('초안 스킬의 리뷰요청 시 검토중으로 전환된다', async () => {
    render(<MarketplacePage />);
    await waitFor(() => screen.getByText('슬랙 통합 리포트 마스터'));

    // 시드: review 1건('문서 자동 분류 봇') 이미 존재
    expect(screen.getAllByText('검토중')).toHaveLength(1);

    // 초안(슬랙 리포트)의 리뷰요청 — draft는 1건뿐이라 버튼도 1개
    await userEvent.click(screen.getByRole('button', { name: /리뷰요청/ }));

    await waitFor(() => {
      expect(screen.getAllByText('검토중')).toHaveLength(2);
    });
    // 초안이 사라져 리뷰요청 버튼도 사라진다
    expect(screen.queryByRole('button', { name: /리뷰요청/ })).not.toBeInTheDocument();
  });
});
