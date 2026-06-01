import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/skills/builder',
}));

const mockCreate = jest.fn();
const mockExtract = jest.fn();
jest.mock('../../../lib/api/skillApi', () => ({
  createPersonalSkill: (...args: unknown[]) => mockCreate(...args),
  streamExtractSkillFromDocument: (...args: unknown[]) => mockExtract(...args),
}));

const mockListDocuments = jest.fn(() => Promise.resolve([] as unknown[]));
jest.mock('../../../lib/api/documentApi', () => ({
  listDocuments: () => mockListDocuments(),
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

const DOC = {
  document_id: 'd1',
  file_name: 'spec.pdf',
  mime_type: 'application/pdf',
  file_size: 2048,
};

beforeEach(() => {
  mockCreate.mockReset();
  mockExtract.mockReset();
  mockPush.mockReset();
  mockListDocuments.mockReset();
  mockListDocuments.mockResolvedValue([]);
  localStorage.clear();
});

describe('SkillBuilderPage — 기반 문서 선택 (REQ-010 association)', () => {
  it('업로드된 문서가 있으면 select 로 기반 문서를 고를 수 있다', async () => {
    mockListDocuments.mockResolvedValue([DOC]);
    render(<SkillBuilderPage />);

    const select = await screen.findByRole('combobox');
    await waitFor(() => expect(select).not.toBeDisabled());
    expect(screen.getByText(/spec\.pdf/)).toBeInTheDocument();
  });

  it('문서 미선택 시 source_document_id 를 전송하지 않는다', async () => {
    mockCreate.mockResolvedValue(CREATED_SKILL);
    const user = userEvent.setup();
    render(<SkillBuilderPage />);

    await user.type(screen.getByPlaceholderText(/주간 리포트 자동화/), '주간 리포트');
    await user.type(screen.getByPlaceholderText(/어떤 작업을 자동화/), '매주 요약 생성');
    await user.click(screen.getByRole('button', { name: '스킬 생성' }));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    const payload = mockCreate.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.source_document_id).toBeUndefined();
    expect(payload.name).toBe('주간 리포트');
    expect(payload.description).toBe('매주 요약 생성');
  });

  it('select 로 고른 문서를 source_document_id 로 전송한다', async () => {
    mockListDocuments.mockResolvedValue([DOC]);
    mockCreate.mockResolvedValue(CREATED_SKILL);
    const user = userEvent.setup();
    render(<SkillBuilderPage />);

    const select = await screen.findByRole('combobox');
    await waitFor(() => expect(select).not.toBeDisabled());
    await user.selectOptions(select, 'd1');
    await user.type(screen.getByPlaceholderText(/주간 리포트 자동화/), '주간 리포트');
    await user.type(screen.getByPlaceholderText(/어떤 작업을 자동화/), '매주 요약 생성');
    await user.click(screen.getByRole('button', { name: '스킬 생성' }));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    const payload = mockCreate.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.source_document_id).toBe('d1');
  });
});

describe('SkillBuilderPage — 문서→빌더 핸드오프 (REQ-010)', () => {
  afterEach(() => {
    window.history.pushState({}, '', '/skills/builder');
  });

  it('source_document_id 쿼리가 있으면 기반 문서를 read-only 로 표시하고 select 를 숨긴다', async () => {
    window.history.pushState({}, '', '/skills/builder?source_document_id=doc-xyz');
    render(<SkillBuilderPage />);

    // 비활성 select 대신 read-only 기반 문서 패널 (목록 미해결 시 id 텍스트로 폴백)
    await waitFor(() => expect(screen.getByText('doc-xyz')).toBeInTheDocument());
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.getByText(/생성 시 문서 연결이 함께 저장/)).toBeInTheDocument();
  });

  it('핸드오프 상태에서 source_document_id 를 백엔드로 전송한다', async () => {
    mockCreate.mockResolvedValue(CREATED_SKILL);
    window.history.pushState({}, '', '/skills/builder?source_document_id=doc-xyz');
    const user = userEvent.setup();
    render(<SkillBuilderPage />);

    await user.type(screen.getByPlaceholderText(/주간 리포트 자동화/), '주간 리포트');
    await user.type(screen.getByPlaceholderText(/어떤 작업을 자동화/), '매주 요약 생성');
    await user.click(screen.getByRole('button', { name: '스킬 생성' }));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    const payload = mockCreate.mock.calls[0][0] as Record<string, unknown>;
    expect(payload).not.toHaveProperty('document_id');
    expect(payload.source_document_id).toBe('doc-xyz');
  });
});

describe('SkillBuilderPage — 문서→스킬 자동 추출 (REQ-010/013 위저드 1단계)', () => {
  afterEach(() => {
    window.history.pushState({}, '', '/skills/builder');
  });

  it('추출 버튼을 누르면 source_document_id 로 추출하고 단일 초안이 폼에 prefill 된다', async () => {
    const user = userEvent.setup();
    window.history.pushState({}, '', '/skills/builder?source_document_id=d1');
    mockListDocuments.mockResolvedValue([DOC]);
    mockExtract.mockImplementation(
      async (_docId: string, onFrame: (f: Record<string, unknown>) => void) => {
        onFrame({
          frame_type: 'result',
          payload: {
            skills: [
              {
                node_type: 'send_report',
                name: '주간 리포트 발송',
                description: '리포트를 슬랙으로 발송',
                instructions: '## When to use\n매주 리포트 발송 시.',
              },
            ],
          },
        });
      },
    );

    render(<SkillBuilderPage />);
    await screen.findByText('기반 문서');
    await user.click(screen.getByRole('button', { name: /이 문서에서 스킬 추출/ }));

    await waitFor(() => expect(mockExtract).toHaveBeenCalledTimes(1));
    expect(mockExtract.mock.calls[0][0]).toBe('d1');

    await waitFor(() =>
      expect(screen.getByPlaceholderText(/주간 리포트 자동화/)).toHaveValue('주간 리포트 발송'),
    );
    expect(screen.getByPlaceholderText(/어떤 작업을 자동화/)).toHaveValue('리포트를 슬랙으로 발송');
  });

  it('추출 결과가 여러 건이면 목록을 보여주고 선택 시 폼에 prefill 된다', async () => {
    const user = userEvent.setup();
    window.history.pushState({}, '', '/skills/builder?source_document_id=d1');
    mockListDocuments.mockResolvedValue([DOC]);
    mockExtract.mockImplementation(
      async (_docId: string, onFrame: (f: Record<string, unknown>) => void) => {
        onFrame({
          frame_type: 'result',
          payload: {
            skills: [
              { node_type: 'a', name: '스킬 A', description: '설명 A', instructions: '## A' },
              { node_type: 'b', name: '스킬 B', description: '설명 B', instructions: '## B' },
            ],
          },
        });
      },
    );

    render(<SkillBuilderPage />);
    await screen.findByText('기반 문서');
    await user.click(screen.getByRole('button', { name: /이 문서에서 스킬 추출/ }));

    await screen.findByText('스킬 A');
    expect(screen.getByText('스킬 B')).toBeInTheDocument();
    // 여러 건이면 자동 prefill 하지 않음
    expect(screen.getByPlaceholderText(/주간 리포트 자동화/)).toHaveValue('');

    await user.click(screen.getByText('스킬 B'));
    expect(screen.getByPlaceholderText(/주간 리포트 자동화/)).toHaveValue('스킬 B');
  });
});
