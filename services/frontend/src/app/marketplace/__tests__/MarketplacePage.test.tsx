import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams('tab=personal'),
  usePathname: () => '/marketplace',
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));

const mockListPersonal = jest.fn();
const mockListMarketplace = jest.fn();
const mockSubmit = jest.fn();
const mockPublish = jest.fn();
const mockDelete = jest.fn();
const mockPromote = jest.fn();
jest.mock('../../../lib/api/skillApi', () => ({
  listPersonalSkills: (...a: unknown[]) => mockListPersonal(...a),
  listMarketplaceSkills: (...a: unknown[]) => mockListMarketplace(...a),
  submitSkill: (...a: unknown[]) => mockSubmit(...a),
  publishSkill: (...a: unknown[]) => mockPublish(...a),
  promoteSkill: (...a: unknown[]) => mockPromote(...a),
  deletePersonalSkill: (...a: unknown[]) => mockDelete(...a),
  archivePersonalSkill: jest.fn(() => Promise.resolve()),
  restorePersonalSkill: jest.fn(() => Promise.resolve()),
  addSkillToWorkflow: jest.fn(() => Promise.resolve()),
}));

jest.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({ role: 'User', userName: 'tester', dept: '', isAuthenticated: true }),
}));

jest.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

import MarketplacePage from '../page';

function personalSkill(over: Partial<Record<string, unknown>> = {}) {
  return {
    skill_id: 'sk-1',
    owner_user_id: 'u1',
    name: '주간 리포트 자동화',
    description: '매주 월요일 OKR 요약 리포트를 자동 생성합니다.',
    node_definition_id: null,
    lifecycle_state: 'draft',
    skill_document_uri: null,
    workflow_id: null,
    source_document_id: null,
    tags: ['리포트', 'OKR'],
    version: '0.1.0',
    promoted_to_team_id: null,
    created_at: '2026-05-20T09:00:00Z',
    updated_at: '2026-05-25T14:30:00Z',
    ...over,
  };
}

beforeEach(() => {
  mockListPersonal.mockReset();
  mockListMarketplace.mockReset();
  mockSubmit.mockReset();
  mockPublish.mockReset();
  mockDelete.mockReset();
  mockPromote.mockReset();
  mockListPersonal.mockResolvedValue([]);
  mockListMarketplace.mockResolvedValue([]);
  mockSubmit.mockResolvedValue(undefined);
  mockPromote.mockResolvedValue(undefined);
});

describe('MarketplacePage — 실 API 연동(Flowit)', () => {
  it('초기 로드 시 스켈레톤을 표시한다', () => {
    mockListPersonal.mockReturnValue(new Promise(() => {}));
    render(<MarketplacePage />);
    expect(document.querySelectorAll('.animate-shimmer').length).toBeGreaterThan(0);
  });

  it('Personal 스킬을 실 listPersonalSkills로 조회해 카드로 렌더링한다', async () => {
    mockListPersonal.mockResolvedValueOnce([personalSkill()]);
    render(<MarketplacePage />);
    await waitFor(() => expect(screen.getByText('주간 리포트 자동화')).toBeInTheDocument());
    expect(mockListPersonal).toHaveBeenCalled();
    expect(screen.getByText('초안')).toBeInTheDocument();
    expect(screen.getByText('v0.1.0')).toBeInTheDocument();
    expect(screen.getByText('내가 만든 스킬')).toBeInTheDocument();
  });

  it('카드 제목이 상세 페이지로 링크된다', async () => {
    mockListPersonal.mockResolvedValueOnce([personalSkill()]);
    render(<MarketplacePage />);
    await waitFor(() => screen.getByText('주간 리포트 자동화'));
    expect(screen.getByText('주간 리포트 자동화').closest('a')).toHaveAttribute('href', '/skills/sk-1');
  });

  it('네트워크 에러 시 메시지 + 재시도로 다시 조회한다', async () => {
    mockListPersonal.mockRejectedValueOnce(new Error('Failed to fetch')).mockResolvedValueOnce([]);
    render(<MarketplacePage />);
    await waitFor(() => expect(screen.getByText('네트워크 연결을 확인해 주세요.')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    await waitFor(() => expect(screen.getByText('등록된 스킬이 없습니다.')).toBeInTheDocument());
    expect(mockListPersonal).toHaveBeenCalledTimes(2);
  });

  it('검색어로 필터링하고, 결과 없으면 안내를 표시한다', async () => {
    mockListPersonal.mockResolvedValueOnce([personalSkill()]);
    render(<MarketplacePage />);
    await waitFor(() => screen.getByText('주간 리포트 자동화'));
    await userEvent.type(screen.getByLabelText('스킬 검색'), '존재하지않는스킬');
    await waitFor(() => {
      expect(screen.getByText("'존재하지않는스킬' 검색 결과가 없습니다.")).toBeInTheDocument();
    });
  });

  it('초안 스킬 리뷰요청 시 submitSkill 호출 + 검토중으로 전환', async () => {
    mockListPersonal.mockResolvedValueOnce([personalSkill()]);
    render(<MarketplacePage />);
    await waitFor(() => screen.getByText('주간 리포트 자동화'));

    await userEvent.click(screen.getByRole('button', { name: /리뷰요청/ }));
    await waitFor(() => expect(mockSubmit).toHaveBeenCalledWith('sk-1', 'personal'));
    await waitFor(() => expect(screen.getByText('검토중')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /검토 대기중/ })).toBeDisabled();
  });

  it('게시된 personal 스킬은 "승격 요청" 버튼으로 promoteSkill(id, "personal") 호출', async () => {
    mockListPersonal.mockResolvedValueOnce([personalSkill({ lifecycle_state: 'published' })]);
    render(<MarketplacePage />);
    await waitFor(() => screen.getByText('주간 리포트 자동화'));

    await userEvent.click(screen.getByRole('button', { name: /승격 요청/ }));
    await waitFor(() => expect(mockPromote).toHaveBeenCalledWith('sk-1', 'personal'));
  });
});
