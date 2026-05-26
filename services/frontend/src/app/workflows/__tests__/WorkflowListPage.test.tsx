import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/workflows',
}));

const mockListWorkflows = jest.fn();
jest.mock('../../../lib/api/workflowApi', () => ({
  listWorkflows: (...args: unknown[]) => mockListWorkflows(...args),
}));

jest.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({ role: 'User', userName: 'tester', dept: '', isAuthenticated: true }),
}));

jest.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ logout: jest.fn() }),
}));

import WorkflowListPage from '../page';

beforeEach(() => mockListWorkflows.mockReset());

describe('WorkflowListPage error handling', () => {
  it('renders error message on network failure', async () => {
    mockListWorkflows.mockRejectedValueOnce(new Error('Failed to fetch'));

    render(<WorkflowListPage />);

    await waitFor(() => {
      expect(screen.getByText('네트워크 연결을 확인해 주세요.')).toBeInTheDocument();
    });
  });

  it('renders server error message on 500', async () => {
    mockListWorkflows.mockRejectedValueOnce(new Error('500 Internal Server Error: '));

    render(<WorkflowListPage />);

    await waitFor(() => {
      expect(screen.getByText('서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.')).toBeInTheDocument();
    });
  });

  it('renders login expired message on 401', async () => {
    mockListWorkflows.mockRejectedValueOnce(new Error('401 Unauthorized: '));

    render(<WorkflowListPage />);

    await waitFor(() => {
      expect(screen.getByText('로그인이 만료되었습니다.')).toBeInTheDocument();
    });
  });

  it('renders retry button and retries on click', async () => {
    mockListWorkflows
      .mockRejectedValueOnce(new Error('Failed to fetch'))
      .mockResolvedValueOnce([]);

    render(<WorkflowListPage />);

    await waitFor(() => {
      expect(screen.getByText('네트워크 연결을 확인해 주세요.')).toBeInTheDocument();
    });

    const retryBtn = screen.getByRole('button', { name: '다시 시도' });
    await userEvent.click(retryBtn);

    await waitFor(() => {
      expect(screen.queryByText('네트워크 연결을 확인해 주세요.')).not.toBeInTheDocument();
      expect(screen.getByText('워크플로우가 없습니다.')).toBeInTheDocument();
    });
    expect(mockListWorkflows).toHaveBeenCalledTimes(2);
  });

  it('renders empty state on success with no data', async () => {
    mockListWorkflows.mockResolvedValueOnce([]);

    render(<WorkflowListPage />);

    await waitFor(() => {
      expect(screen.getByText('워크플로우가 없습니다.')).toBeInTheDocument();
    });
  });
});
