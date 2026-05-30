import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/skills/builder',
}));

const mockCreate = jest.fn();
jest.mock('../../../lib/api/skillApi', () => ({
  createPersonalSkill: (...args: unknown[]) => mockCreate(...args),
}));

jest.mock('../../../lib/api/documentApi', () => ({
  listDocuments: jest.fn(() => Promise.resolve([])),
}));

jest.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({ role: 'User', userName: 'tester', dept: '', isAuthenticated: true }),
}));

jest.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

import SkillBuilderPage from '../builder/page';

const CREATED_SKILL = {
  skill_id: 'sk-new',
  owner_user_id: 'u1',
  name: '주간 리포트',
  description: '매주 요약 생성',
  node_definition_id: null,
  lifecycle_state: 'draft' as const,
  skill_document_uri: null,
  workflow_id: null,
  tags: [],
  version: '0.1.0',
  promoted_to_team_id: null,
  created_at: '2026-05-29T09:00:00Z',
  updated_at: '2026-05-29T09:00:00Z',
};

beforeEach(() => {
  mockCreate.mockReset();
  mockPush.mockReset();
  localStorage.clear();
});

describe('SkillBuilderPage — 기반 문서 선택 (PR #216 리뷰 #1)', () => {
  it('문서 선택 select 는 백엔드 연동 전까지 비활성화돼 있다', () => {
    localStorage.setItem(
      'wf_documents_list',
      JSON.stringify([
        { document_id: 'd1', file_name: 'spec.pdf', mime_type: 'application/pdf', file_size: 2048 },
      ]),
    );
    render(<SkillBuilderPage />);

    const select = screen.getByRole('combobox');
    expect(select).toBeDisabled();
    expect(screen.getByText(/백엔드 연동 후 활성화/)).toBeInTheDocument();
  });

  it('스킬 생성 시 document_id 를 백엔드로 전송하지 않는다 (false healthy 방지)', async () => {
    mockCreate.mockResolvedValue(CREATED_SKILL);
    const user = userEvent.setup();
    render(<SkillBuilderPage />);

    await user.type(screen.getByPlaceholderText(/주간 리포트 자동화/), '주간 리포트');
    await user.type(screen.getByPlaceholderText(/어떤 작업을 자동화/), '매주 요약 생성');
    await user.click(screen.getByRole('button', { name: '스킬 생성' }));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    const payload = mockCreate.mock.calls[0][0] as Record<string, unknown>;
    expect(payload).not.toHaveProperty('document_id');
    expect(payload.name).toBe('주간 리포트');
    expect(payload.description).toBe('매주 요약 생성');
  });
});
