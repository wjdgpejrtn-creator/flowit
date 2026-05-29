import { getLatestExecution } from '../workflowApi';

jest.mock('../../apiClient', () => ({
  apiJson: jest.fn(),
}));

import { apiJson } from '../../apiClient';
const mockApiJson = apiJson as jest.MockedFunction<typeof apiJson>;

beforeEach(() => {
  mockApiJson.mockReset();
});

describe('getLatestExecution', () => {
  it('정상 응답을 그대로 반환한다 (running)', async () => {
    const exec = {
      execution_id: 'exec-1',
      workflow_id: 'wf-1',
      status: 'running' as const,
      started_at: '2026-05-28T10:00:00Z',
      finished_at: null,
      error: null,
      node_states_summary: { running: 1, succeeded: 2 },
      node_results: [
        { node_instance_id: 'n1', status: 'succeeded' as const, attempt: 0, last_error: null },
      ],
    };
    mockApiJson.mockResolvedValueOnce(exec);

    const result = await getLatestExecution('wf-1');

    expect(result).toEqual(exec);
    expect(mockApiJson).toHaveBeenCalledWith('/api/v1/workflows/wf-1/executions/latest');
  });

  it('실행 0건이면 null을 반환한다 (200 + null)', async () => {
    mockApiJson.mockResolvedValueOnce(null);

    const result = await getLatestExecution('wf-no-exec');

    expect(result).toBeNull();
    expect(mockApiJson).toHaveBeenCalledWith('/api/v1/workflows/wf-no-exec/executions/latest');
  });

  it('apiJson 실패 시 에러를 throw한다 (호출자가 catch 책임)', async () => {
    mockApiJson.mockRejectedValueOnce(new Error('500 Internal Server Error: boom'));

    await expect(getLatestExecution('wf-fail')).rejects.toThrow('500 Internal Server Error');
  });
});
