import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockListReviewQueue = jest.fn();
const mockApprove = jest.fn();
const mockPublish = jest.fn();
jest.mock('../../../../lib/api/skillApi', () => ({
  listReviewQueue: (...a: unknown[]) => mockListReviewQueue(...a),
  approveSkill: (...a: unknown[]) => mockApprove(...a),
  publishSkill: (...a: unknown[]) => mockPublish(...a),
}));
jest.mock('../../../../stores/toastStore', () => ({ showToast: jest.fn() }));

import AdminApprovalsPage from '../page';

function reviewItem(over: Partial<Record<string, unknown>> = {}) {
  return {
    skill_id: 'sk-1',
    scope: 'team',
    name: '승격 요청 스킬',
    description: 'personal에서 team으로 승격됨',
    lifecycle_state: 'review',
    owner_user_id: null,
    tags: [],
    version: '0.1.0',
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-06-01T00:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  mockListReviewQueue.mockReset();
  mockApprove.mockReset();
  mockPublish.mockReset();
  mockApprove.mockResolvedValue(undefined);
  mockPublish.mockResolvedValue(undefined);
  // personal/team/company 3 scope 병렬 조회 — team에만 1건.
  mockListReviewQueue.mockImplementation((scope: string) =>
    Promise.resolve(scope === 'team' ? [reviewItem()] : []),
  );
});

describe('AdminApprovalsPage — 리뷰/승격 승인 큐', () => {
  it('3 scope를 합쳐 항목을 렌더하고 승인→게시 2단계로 처리한다', async () => {
    render(<AdminApprovalsPage />);
    await waitFor(() => expect(screen.getByText('승격 요청 스킬')).toBeInTheDocument());
    // 3 scope 병렬 조회
    expect(mockListReviewQueue).toHaveBeenCalledWith('personal');
    expect(mockListReviewQueue).toHaveBeenCalledWith('team');
    expect(mockListReviewQueue).toHaveBeenCalledWith('company');

    // 승인(REVIEW→APPROVED) — item.scope 그대로 전달
    await userEvent.click(screen.getByRole('button', { name: /승인/ }));
    await waitFor(() => expect(mockApprove).toHaveBeenCalledWith('sk-1', 'team', true));

    // 승인 후 게시 버튼 노출 → 게시(APPROVED→PUBLISHED)
    const publishBtn = await screen.findByRole('button', { name: /게시/ });
    await userEvent.click(publishBtn);
    await waitFor(() => expect(mockPublish).toHaveBeenCalledWith('sk-1', 'team'));

    // 게시되면 큐에서 제거
    await waitFor(() => expect(screen.queryByText('승격 요청 스킬')).not.toBeInTheDocument());
  });

  it('한 scope만 실패해도 나머지 정상 항목은 표시한다 (allSettled 부분 성공)', async () => {
    mockListReviewQueue.mockImplementation((scope: string) =>
      scope === 'company'
        ? Promise.reject(new Error('500 server error'))
        : Promise.resolve(scope === 'team' ? [reviewItem()] : []),
    );
    render(<AdminApprovalsPage />);
    await waitFor(() => expect(screen.getByText('승격 요청 스킬')).toBeInTheDocument());
    // 부분 실패라도 에러 화면으로 전체를 가리지 않는다
    expect(screen.queryByText('관리자 권한이 필요합니다.')).not.toBeInTheDocument();
  });

  it('비-Admin(403)이면 권한 안내를 표시한다', async () => {
    mockListReviewQueue.mockRejectedValue(new Error('403 Forbidden'));
    render(<AdminApprovalsPage />);
    await waitFor(() =>
      expect(screen.getByText('관리자 권한이 필요합니다.')).toBeInTheDocument(),
    );
  });

  it('빈 큐면 안내를 표시한다', async () => {
    mockListReviewQueue.mockResolvedValue([]);
    render(<AdminApprovalsPage />);
    await waitFor(() =>
      expect(screen.getByText('대기 중인 승인 요청이 없습니다.')).toBeInTheDocument(),
    );
  });
});
