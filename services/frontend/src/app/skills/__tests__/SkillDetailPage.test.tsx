import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = jest.fn();
let mockId = 'sk-001';
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => ({ id: mockId }),
  usePathname: () => '/skills/test-id',
}));

const mockGet = jest.fn();
const mockUpdate = jest.fn();
const mockDelete = jest.fn();
jest.mock('../../../lib/api/skillApi', () => ({
  getPersonalSkill: (...args: unknown[]) => mockGet(...args),
  updatePersonalSkill: (...args: unknown[]) => mockUpdate(...args),
  deletePersonalSkill: (...args: unknown[]) => mockDelete(...args),
}));

jest.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({ role: 'User', userName: 'tester', dept: '', isAuthenticated: true }),
}));

jest.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

import SkillDetailPage from '../[id]/page';

beforeEach(() => {
  mockGet.mockReset();
  mockUpdate.mockReset();
  mockDelete.mockReset();
  mockPush.mockReset();
});

const DRAFT_SKILL = {
  skill_id: 'sk-001',
  owner_user_id: 'u1',
  name: '주간 리포트',
  description: '매주 OKR 요약 생성',
  node_definition_id: null,
  lifecycle_state: 'draft' as const,
  skill_document_uri: null,
  workflow_id: null,
  tags: ['리포트'],
  version: '0.1.0',
  promoted_to_team_id: null,
  created_at: '2026-05-20T09:00:00Z',
  updated_at: '2026-05-25T14:30:00Z',
};

const PUBLISHED_SKILL = { ...DRAFT_SKILL, skill_id: 'sk-002', lifecycle_state: 'published' as const };

function renderPage() {
  mockId = DRAFT_SKILL.skill_id;
  return render(<SkillDetailPage />);
}

function renderPublishedPage() {
  mockId = PUBLISHED_SKILL.skill_id;
  return render(<SkillDetailPage />);
}

describe('SkillDetailPage', () => {
  /* ── 조회 ── */

  it('로딩 중 스켈레톤을 표시한다', () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    renderPage();
    const skeletons = document.querySelectorAll('.animate-shimmer');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('스킬 정보를 렌더링한다', async () => {
    mockGet.mockResolvedValueOnce(DRAFT_SKILL);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('매주 OKR 요약 생성')).toBeInTheDocument();
    });
    expect(screen.getAllByText('주간 리포트').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('리포트')).toBeInTheDocument();
    expect(screen.getByText('v0.1.0')).toBeInTheDocument();
  });

  it('404 에러 시 메시지를 표시한다', async () => {
    mockGet.mockRejectedValueOnce(new Error('404 Not Found: '));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('스킬을 찾을 수 없습니다.')).toBeInTheDocument();
    });
  });

  it('403 에러 시 권한 없음 메시지를 표시한다', async () => {
    mockGet.mockRejectedValueOnce(new Error('403 Forbidden: '));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('이 스킬에 접근할 권한이 없습니다.')).toBeInTheDocument();
    });
  });

  /* ── DRAFT 제약 ── */

  it('DRAFT 스킬에 수정/삭제 버튼이 보인다', async () => {
    mockGet.mockResolvedValueOnce(DRAFT_SKILL);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '수정' })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '삭제' })).toBeInTheDocument();
  });

  it('PUBLISHED 스킬에는 수정/삭제 버튼이 없다', async () => {
    mockGet.mockResolvedValueOnce(PUBLISHED_SKILL);
    renderPublishedPage();

    await waitFor(() => {
      expect(screen.getAllByText('게시됨').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByRole('button', { name: '수정' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '삭제' })).not.toBeInTheDocument();
  });

  /* ── 편집 ── */

  it('수정 버튼 클릭 → 폼 표시 → 저장 호출', async () => {
    mockGet.mockResolvedValueOnce(DRAFT_SKILL);
    const updated = { ...DRAFT_SKILL, name: '월간 리포트' };
    mockUpdate.mockResolvedValueOnce(updated);

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '수정' })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: '수정' }));

    const nameInput = screen.getByDisplayValue('주간 리포트');
    expect(nameInput).toBeInTheDocument();

    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, '월간 리포트');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith('sk-001', {
        name: '월간 리포트',
        description: '매주 OKR 요약 생성',
        tags: ['리포트'],
      });
    });
  });

  it('편집 취소 시 폼이 닫힌다', async () => {
    mockGet.mockResolvedValueOnce(DRAFT_SKILL);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '수정' })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: '수정' }));
    expect(screen.getByDisplayValue('주간 리포트')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '취소' }));

    await waitFor(() => {
      expect(screen.queryByDisplayValue('주간 리포트')).not.toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '수정' })).toBeInTheDocument();
  });

  /* ── 삭제 ── */

  it('삭제 → 확인 → 삭제 완료 후 목록으로 이동', async () => {
    mockGet.mockResolvedValueOnce(DRAFT_SKILL);
    mockDelete.mockResolvedValueOnce(undefined);

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '삭제' })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: '삭제' }));
    expect(screen.getByRole('button', { name: '정말 삭제' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '정말 삭제' }));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith('sk-001');
      expect(mockPush).toHaveBeenCalledWith('/marketplace?tab=personal');
    });
  });

  it('삭제 확인 단계에서 취소하면 원래로 돌아간다', async () => {
    mockGet.mockResolvedValueOnce(DRAFT_SKILL);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '삭제' })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: '삭제' }));
    expect(screen.getByRole('button', { name: '정말 삭제' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '취소' }));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '정말 삭제' })).not.toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '삭제' })).toBeInTheDocument();
  });
});
