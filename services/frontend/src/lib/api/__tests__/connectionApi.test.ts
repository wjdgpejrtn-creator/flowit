import { getConnections } from '../connectionApi';

jest.mock('../../apiClient', () => ({
  apiJson: jest.fn(),
}));

import { apiJson } from '../../apiClient';
const mockApiJson = apiJson as jest.MockedFunction<typeof apiJson>;

beforeEach(() => {
  mockApiJson.mockReset();
});

describe('getConnections', () => {
  it('GET /api/v1/connections 호출 후 응답 배열을 그대로 반환한다', async () => {
    const rows = [
      { service: 'google', display: 'u@x.com', connected: true, status: 'connected' },
      { service: 'slack', display: 'flowit-team', connected: true, status: 'connected' },
      { service: 'erp', display: null, connected: false, status: 'expired' },
    ];
    mockApiJson.mockResolvedValueOnce(rows);

    const result = await getConnections();

    expect(result).toEqual(rows);
    expect(mockApiJson).toHaveBeenCalledWith('/api/v1/connections');
  });

  it('연결 0건이면 빈 배열을 반환한다', async () => {
    mockApiJson.mockResolvedValueOnce([]);

    const result = await getConnections();

    expect(result).toEqual([]);
    expect(mockApiJson).toHaveBeenCalledWith('/api/v1/connections');
  });

  it('display가 null이어도 그대로 전달한다 (호출부에서 fallback 처리)', async () => {
    mockApiJson.mockResolvedValueOnce([{ service: 'google', display: null, connected: true, status: 'connected' }]);

    const result = await getConnections();

    expect(result[0].display).toBeNull();
    expect(result[0].connected).toBe(true);
  });

  it('apiJson 실패 시 에러를 throw한다 (호출자가 catch 책임)', async () => {
    mockApiJson.mockRejectedValueOnce(new Error('500 Internal Server Error: boom'));

    await expect(getConnections()).rejects.toThrow('500 Internal Server Error');
  });
});
