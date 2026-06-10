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
const mockExtractDetail = jest.fn();
const mockCreatePersonal = jest.fn();
const mockListTemplates = jest.fn();
const mockSelfPublish = jest.fn();
const mockGetPersonal = jest.fn();
jest.mock('../../../lib/api/skillApi', () => ({
  streamExtractSkill: (...args: unknown[]) => mockStreamExtract(...args),
  extractSkillDetail: (...args: unknown[]) => mockExtractDetail(...args),
  createPersonalSkill: (...args: unknown[]) => mockCreatePersonal(...args),
  listSkillTemplates: (...args: unknown[]) => mockListTemplates(...args),
  selfPublishPersonalSkill: (...args: unknown[]) => mockSelfPublish(...args),
  getPersonalSkill: (...args: unknown[]) => mockGetPersonal(...args),
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
  mockExtractDetail.mockReset();
  mockCreatePersonal.mockReset();
  mockListTemplates.mockReset();
  mockListDocuments.mockReset();
  mockPush.mockReset();
  mockSelfPublish.mockReset();
  mockGetPersonal.mockReset();
  mockListDocuments.mockResolvedValue([]);
  mockListTemplates.mockResolvedValue([]);
  mockSelfPublish.mockResolvedValue(undefined);
  // 메타 선택 시 2차 detail 호출 — 기본은 instructions/staging 채움(#353 2단계). 테스트가 덮어쓸 수 있다.
  mockExtractDetail.mockResolvedValue({ node_type: 'a', instructions: '## A', staging: STAGING });
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
    onFrame({ frame_type: 'result', payload: { skill_metas: [
      { node_type: 'send_report', name: '주간 리포트 발송', description: '리포트 발송', category: 'action', risk_level: 'Low' },
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
    onFrame({ frame_type: 'result', payload: { skill_metas: [
      { node_type: 'a', name: '스킬 A', description: 'A 설명', category: 'action', risk_level: 'Low' },
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
    onFrame({ frame_type: 'result', payload: { skill_metas: [
      { node_type: 'x', name: '스킬 X', description: 'X 설명', category: 'action', risk_level: 'Low' },
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

const STAGING = {
  category: 'integration',
  input_schema: { type: 'object', properties: { x: { type: 'string' } } },
  output_schema: { type: 'object' },
  risk_level: 'Medium',
  required_connections: ['slack'],
  service_type: 'slack',
};

function _draftFrame(onFrame: (f: Record<string, unknown>) => void) {
  // 1차는 메타 5필드만 — instructions/staging은 선택 후 2차 extractSkillDetail(mock)이 채운다(#353).
  onFrame({ frame_type: 'result', payload: { skill_metas: [
    { node_type: 'a', name: '스킬 A', description: 'A 설명', category: 'integration', risk_level: 'Medium' },
  ] } });
}

test('검토 & 게시: source_document_id + staging 전송 후 self-publish 체인 실행', async () => {
  mockCreatePersonal.mockResolvedValue(CREATED);
  mockGetPersonal.mockResolvedValue({ ...CREATED, lifecycle_state: 'published' });
  mockStreamExtract.mockImplementation(async (_m: unknown, onFrame: (f: Record<string, unknown>) => void) => _draftFrame(onFrame));
  const user = userEvent.setup();

  window.history.pushState({}, '', '/skills/builder?source_document_id=doc-7');
  render(<SkillBuilderPage />);
  await waitFor(() => expect(screen.getByPlaceholderText(/주간 리포트 자동화/)).toHaveValue('스킬 A'));
  await user.click(screen.getByRole('button', { name: '검토 & 게시' }));

  await waitFor(() => expect(mockCreatePersonal).toHaveBeenCalledTimes(1));
  const payload = mockCreatePersonal.mock.calls[0][0] as Record<string, unknown>;
  expect(payload.source_document_id).toBe('doc-7');
  // 추출 초안의 staging이 그대로 전송(publish 노드 I/O)
  expect((payload.node_spec_staging as Record<string, unknown>).category).toBe('integration');
  // self-publish 체인 실행 + 게시 결과 재조회
  await waitFor(() => expect(mockSelfPublish).toHaveBeenCalledWith('sk-1'));
  expect(mockGetPersonal).toHaveBeenCalledWith('sk-1');
});

test('초안 저장: create만 호출, self-publish 미실행 / 템플릿갈래는 source_document_id 미전송', async () => {
  mockCreatePersonal.mockResolvedValue(CREATED);
  mockListTemplates.mockResolvedValue([
    { code: 'ecommerce', name: '이커머스', description: '주문', kind: 'industry' },
  ]);
  mockStreamExtract.mockImplementation(async (_m: unknown, onFrame: (f: Record<string, unknown>) => void) => _draftFrame(onFrame));
  const user = userEvent.setup();

  window.history.pushState({}, '', '/skills/builder');
  render(<SkillBuilderPage />);
  await user.click(await screen.findByText(/아니요, 직접 만들게요/));
  await user.click(await screen.findByText('이커머스'));
  await waitFor(() => expect(screen.getByPlaceholderText(/주간 리포트 자동화/)).toHaveValue('스킬 A'));
  await user.click(screen.getByRole('button', { name: '초안 저장' }));

  await waitFor(() => expect(mockCreatePersonal).toHaveBeenCalledTimes(1));
  expect((mockCreatePersonal.mock.calls[0][0] as Record<string, unknown>).source_document_id).toBeUndefined();
  // 초안 저장은 self-publish 안 함
  expect(mockSelfPublish).not.toHaveBeenCalled();
});

test('다건 메타: payload.skill_metas로 카드 노출 → 선택 시 extractSkillDetail로 detail 채움 (#353 계약)', async () => {
  // #353 회귀 가드: 백엔드가 1차에 payload.skill_metas(메타 목록)를 보내고, 사용자가 1건
  // 선택하면 2차 extractSkillDetail로 instructions/staging을 채운다. 과거엔 프론트가 payload.skills를
  // 읽어 항상 빈 목록이 됐다(추출 초안이 안 떴다). 다건이라 자동선택 없이 카드 클릭 경로를 검증한다.
  mockStreamExtract.mockImplementation(async (_m: unknown, onFrame: (f: Record<string, unknown>) => void) => {
    onFrame({ frame_type: 'result', payload: { skill_metas: [
      { node_type: 'a', name: '스킬 A', description: 'A 설명', category: 'action', risk_level: 'Low' },
      { node_type: 'b', name: '스킬 B', description: 'B 설명', category: 'integration', risk_level: 'Medium' },
    ] } });
  });
  mockExtractDetail.mockResolvedValue({ node_type: 'b', instructions: '## B 지침', staging: STAGING });
  const user = userEvent.setup();

  window.history.pushState({}, '', '/skills/builder?source_document_id=doc-9');
  render(<SkillBuilderPage />);

  // 다건이므로 자동 prefill 없음 — 두 카드가 모두 떠야 한다(skill_metas를 읽었다는 증거).
  await waitFor(() => expect(screen.getByText('2개의 초안이 추출됐습니다. 하나를 선택하면 아래 폼에 채워집니다.')).toBeInTheDocument());
  expect(screen.getByText('스킬 A')).toBeInTheDocument();
  expect(screen.getByText('스킬 B')).toBeInTheDocument();
  expect(mockExtractDetail).not.toHaveBeenCalled();

  // 스킬 B 카드 선택 → 2차 detail 호출(material + 선택 meta) → instructions 폼 채움.
  await user.click(screen.getByText('스킬 B'));
  await waitFor(() => expect(mockExtractDetail).toHaveBeenCalledWith(
    { source_document_id: 'doc-9' },
    expect.objectContaining({ node_type: 'b', name: '스킬 B' }),
  ));
  await waitFor(() => expect(screen.getByPlaceholderText(/주간 리포트 자동화/)).toHaveValue('스킬 B'));
  await waitFor(() => expect(screen.getByDisplayValue('## B 지침')).toBeInTheDocument());
});
