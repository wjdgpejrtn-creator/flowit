/**
 * SkillBuilderPage — 위저드 재설계(첫화면 문서 有無 분기 + 문서/템플릿 추출 합류) 테스트.
 *
 * 검증축:
 * - 첫 화면: "문서가 있으신가요?" 분기 노출(문서 / 직접 만들기)
 * - 핸드오프(?source_document_id=) → 첫 화면 건너뛰고 바로 추출(자동 실행 + 단일 prefill)
 * - 문서 분기: 문서 선택 → 추출(source_document_id) → 초안 목록
 * - 템플릿 분기: 직접 만들기 → 템플릿 카드 → 추출(template_code)
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => '/skills/builder',
}));

const mockStreamExtract = jest.fn();
const mockCreatePersonal = jest.fn();
const mockListTemplates = jest.fn();
jest.mock('../../../lib/api/skillApi', () => ({
  streamExtractSkill: (...args: unknown[]) => mockStreamExtract(...args),
  createPersonalSkill: (...args: unknown[]) => mockCreatePersonal(...args),
  listSkillTemplates: (...args: unknown[]) => mockListTemplates(...args),
}));

const mockListDocuments = jest.fn();
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

const DOC = {
  document_id: 'd1',
  file_name: 'spec.pdf',
  mime_type: 'application/pdf',
  file_size: 2048,
};

beforeEach(() => {
  mockStreamExtract.mockReset();
  mockCreatePersonal.mockReset();
  mockListTemplates.mockReset();
  mockListDocuments.mockReset();
  mockPush.mockReset();
  mockListDocuments.mockResolvedValue([]);
  mockListTemplates.mockResolvedValue([]);
  window.history.pushState({}, '', '/skills/builder');
});

afterEach(() => {
  window.history.pushState({}, '', '/skills/builder');
});

test('첫 화면에 문서 有無 분기가 노출된다', async () => {
  render(<SkillBuilderPage />);
  await waitFor(() => {
    expect(screen.getByText('업무 관련 문서가 있으신가요?')).toBeInTheDocument();
  });
  expect(screen.getByText(/네, 문서가 있어요/)).toBeInTheDocument();
  expect(screen.getByText(/아니요, 직접 만들게요/)).toBeInTheDocument();
});

test('핸드오프 진입 시 첫 화면을 건너뛰고 자동 추출 + 단일 prefill', async () => {
  mockStreamExtract.mockImplementation(async (_material: unknown, onFrame: (f: Record<string, unknown>) => void) => {
    onFrame({ frame_type: 'result', payload: { skills: [
      { node_type: 'send_report', name: '주간 리포트 발송', description: '리포트 발송', instructions: '## When' },
    ] } });
  });
  window.history.pushState({}, '', '/skills/builder?source_document_id=doc-1');
  render(<SkillBuilderPage />);

  await waitFor(() => expect(screen.getByText(/문서에서 자동 추출/)).toBeInTheDocument());
  expect(mockStreamExtract).toHaveBeenCalledWith(
    { source_document_id: 'doc-1' }, expect.any(Function), expect.any(AbortSignal),
  );
  await waitFor(() =>
    expect(screen.getByPlaceholderText(/주간 리포트 자동화/)).toHaveValue('주간 리포트 발송'),
  );
});

test('문서 분기: 문서 선택 → source_document_id로 추출', async () => {
  mockListDocuments.mockResolvedValue([DOC]);
  mockStreamExtract.mockImplementation(async (_material: unknown, onFrame: (f: Record<string, unknown>) => void) => {
    onFrame({ frame_type: 'result', payload: { skills: [
      { node_type: 'a', name: '스킬 A', description: 'A 설명', instructions: '## A' },
    ] } });
  });
  const user = userEvent.setup();
  render(<SkillBuilderPage />);

  await waitFor(() => screen.getByText(/네, 문서가 있어요/));
  await user.click(screen.getByText(/네, 문서가 있어요/));
  const select = await screen.findByRole('combobox');
  await waitFor(() => expect(select).not.toBeDisabled());
  await user.selectOptions(select, 'd1');
  await user.click(screen.getByRole('button', { name: /이 문서로 시작/ }));

  await waitFor(() => expect(mockStreamExtract).toHaveBeenCalledWith(
    { source_document_id: 'd1' }, expect.any(Function), expect.any(AbortSignal),
  ));
});

test('템플릿 분기: 직접 만들기 → 카드 선택 → template_code로 추출', async () => {
  mockListTemplates.mockResolvedValue([
    { code: 'ecommerce', name: '이커머스', description: '주문·재고·리뷰', kind: 'industry' },
    { code: 'marketing', name: '마케팅', description: '캠페인·리드', kind: 'functional' },
  ]);
  mockStreamExtract.mockImplementation(async (_material: unknown, onFrame: (f: Record<string, unknown>) => void) => {
    onFrame({ frame_type: 'result', payload: { skills: [
      { node_type: 'x', name: '스킬 X', description: 'X 설명', instructions: '## X' },
    ] } });
  });
  const user = userEvent.setup();
  render(<SkillBuilderPage />);

  await waitFor(() => screen.getByText(/아니요, 직접 만들게요/));
  await user.click(screen.getByText(/아니요, 직접 만들게요/));
  await waitFor(() => expect(mockListTemplates).toHaveBeenCalled());
  await user.click(await screen.findByText('이커머스'));

  await waitFor(() => expect(mockStreamExtract).toHaveBeenCalledWith(
    { template_code: 'ecommerce' }, expect.any(Function), expect.any(AbortSignal),
  ));
});

const CREATED = {
  skill_id: 'sk-1', owner_user_id: 'u1', name: 'n', description: 'd',
  node_definition_id: null, lifecycle_state: 'draft', skill_document_uri: null,
  workflow_id: null, source_document_id: null, tags: [], version: '0.1.0',
  promoted_to_team_id: null, created_at: '2026-06-01T00:00:00Z', updated_at: '2026-06-01T00:00:00Z',
};

test('생성: 문서갈래는 source_document_id 전송 / 템플릿갈래는 미전송 (association SSOT)', async () => {
  mockCreatePersonal.mockResolvedValue(CREATED);
  mockStreamExtract.mockImplementation(async (_m: unknown, onFrame: (f: Record<string, unknown>) => void) => {
    onFrame({ frame_type: 'result', payload: { skills: [
      { node_type: 'a', name: '스킬 A', description: 'A 설명', instructions: '## A' },
    ] } });
  });
  const user = userEvent.setup();

  // 문서갈래(핸드오프) → 생성 시 source_document_id 전송
  window.history.pushState({}, '', '/skills/builder?source_document_id=doc-7');
  const { unmount } = render(<SkillBuilderPage />);
  await waitFor(() => expect(screen.getByPlaceholderText(/주간 리포트 자동화/)).toHaveValue('스킬 A'));
  await user.click(screen.getByRole('button', { name: '스킬 생성' }));
  await waitFor(() => expect(mockCreatePersonal).toHaveBeenCalledTimes(1));
  expect((mockCreatePersonal.mock.calls[0][0] as Record<string, unknown>).source_document_id).toBe('doc-7');
  unmount();

  // 템플릿갈래 → 생성 시 source_document_id 미전송(undefined)
  mockCreatePersonal.mockClear();
  mockListTemplates.mockResolvedValue([
    { code: 'ecommerce', name: '이커머스', description: '주문', kind: 'industry' },
  ]);
  window.history.pushState({}, '', '/skills/builder');
  render(<SkillBuilderPage />);
  await user.click(await screen.findByText(/아니요, 직접 만들게요/));
  await user.click(await screen.findByText('이커머스'));
  await waitFor(() => expect(screen.getByPlaceholderText(/주간 리포트 자동화/)).toHaveValue('스킬 A'));
  await user.click(screen.getByRole('button', { name: '스킬 생성' }));
  await waitFor(() => expect(mockCreatePersonal).toHaveBeenCalledTimes(1));
  expect((mockCreatePersonal.mock.calls[0][0] as Record<string, unknown>).source_document_id).toBeUndefined();
});
