import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams('tab=personal'),
  usePathname: () => '/marketplace',
}));

const mockListPersonalSkills = jest.fn();
jest.mock('../../../lib/api/skillApi', () => ({
  listPersonalSkills: (...args: unknown[]) => mockListPersonalSkills(...args),
}));

jest.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({ role: 'User', userName: 'tester', dept: '', isAuthenticated: true }),
}));

jest.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

import MarketplacePage from '../page';

beforeEach(() => mockListPersonalSkills.mockReset());

const MOCK_SKILL = {
  skill_id: '00000000-0000-0000-0000-000000000001',
  owner_user_id: 'u1',
  name: '주간 리포트 자동화',
  description: '매주 월요일 OKR 요약 리포트를 자동 생성합니다.',
  node_definition_id: null,
  lifecycle_state: 'draft' as const,
  skill_document_uri: null,
  workflow_id: null,
  tags: ['리포트', 'OKR'],
  version: '0.1.0',
  promoted_to_team_id: null,
  created_at: '2026-05-20T09:00:00Z',
  updated_at: '2026-05-25T14:30:00Z',
};

describe('MarketplacePage — Personal 탭', () => {
  it('로딩 중 스켈레톤을 표시한다', () => {
    mockListPersonalSkills.mockReturnValue(new Promise(() => {}));
    render(<MarketplacePage />);
    const skeletons = document.querySelectorAll('.animate-shimmer');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('네트워크 에러 시 메시지와 재시도 버튼을 표시한다', async () => {
    mockListPersonalSkills.mockRejectedValueOnce(new Error('Failed to fetch'));
    render(<MarketplacePage />);

    await waitFor(() => {
      expect(screen.getByText('네트워크 연결을 확인해 주세요.')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument();
  });

  it('재시도 버튼 클릭 시 다시 호출한다', async () => {
    mockListPersonalSkills
      .mockRejectedValueOnce(new Error('Failed to fetch'))
      .mockResolvedValueOnce([]);
    render(<MarketplacePage />);

    await waitFor(() => {
      expect(screen.getByText('네트워크 연결을 확인해 주세요.')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));

    await waitFor(() => {
      expect(screen.getByText('등록된 개인 스킬이 없습니다.')).toBeInTheDocument();
    });
    expect(mockListPersonalSkills).toHaveBeenCalledTimes(2);
  });

  it('서버 에러(500) 시 적절한 메시지를 표시한다', async () => {
    mockListPersonalSkills.mockRejectedValueOnce(new Error('500 Internal Server Error: '));
    render(<MarketplacePage />);

    await waitFor(() => {
      expect(screen.getByText('서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.')).toBeInTheDocument();
    });
  });

  it('빈 목록이면 안내 메시지를 표시한다', async () => {
    mockListPersonalSkills.mockResolvedValueOnce([]);
    render(<MarketplacePage />);

    await waitFor(() => {
      expect(screen.getByText('등록된 개인 스킬이 없습니다.')).toBeInTheDocument();
    });
  });

  it('스킬 카드를 렌더링한다', async () => {
    mockListPersonalSkills.mockResolvedValueOnce([MOCK_SKILL]);
    render(<MarketplacePage />);

    await waitFor(() => {
      expect(screen.getByText('주간 리포트 자동화')).toBeInTheDocument();
    });
    expect(screen.getByText('매주 월요일 OKR 요약 리포트를 자동 생성합니다.')).toBeInTheDocument();
    expect(screen.getByText('리포트')).toBeInTheDocument();
    expect(screen.getByText('초안')).toBeInTheDocument();
    expect(screen.getByText('v0.1.0')).toBeInTheDocument();
  });

  it('스킬 카드가 상세 페이지로 링크된다', async () => {
    mockListPersonalSkills.mockResolvedValueOnce([MOCK_SKILL]);
    render(<MarketplacePage />);

    await waitFor(() => {
      expect(screen.getByText('주간 리포트 자동화')).toBeInTheDocument();
    });

    const card = screen.getByText('주간 리포트 자동화').closest('a');
    expect(card).toHaveAttribute('href', `/skills/${MOCK_SKILL.skill_id}`);
  });
});
