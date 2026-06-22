import { apiFetch, apiJson } from '@/lib/apiClient';

const mockFetch = jest.fn();
global.fetch = mockFetch;

const makeRes = (body: string, status: number, statusText = '') => ({
  ok: status >= 200 && status < 300,
  status,
  statusText,
  json: () => Promise.resolve(JSON.parse(body || 'null')),
  text: () => Promise.resolve(body),
});

beforeEach(() => {
  mockFetch.mockReset();
});

describe('apiFetch — 401 → refresh → retry', () => {
  it('returns response directly on 200', async () => {
    mockFetch.mockResolvedValueOnce(makeRes('{}', 200));

    const res = await apiFetch('/api/test');

    expect(res.status).toBe(200);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('retries once after 401 when refresh succeeds', async () => {
    mockFetch
      .mockResolvedValueOnce(makeRes('', 401))           // 원본 요청 401
      .mockResolvedValueOnce(makeRes('{}', 200))         // /api/v1/auth/refresh 성공
      .mockResolvedValueOnce(makeRes('{"ok":true}', 200)); // 재시도 성공

    const res = await apiFetch('/api/test');

    expect(res.status).toBe(200);
    expect(mockFetch).toHaveBeenCalledTimes(3);
    expect(mockFetch.mock.calls[1][0]).toBe('/api/v1/auth/refresh');
  });

  it('throws Session expired when refresh also fails', async () => {
    mockFetch
      .mockResolvedValueOnce(makeRes('', 401)) // 원본 401
      .mockResolvedValueOnce(makeRes('', 401)); // refresh도 실패

    await expect(apiFetch('/api/test')).rejects.toThrow('Session expired');
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('does not retry on non-401 errors', async () => {
    mockFetch.mockResolvedValueOnce(makeRes('Not Found', 404));

    const res = await apiFetch('/api/test');

    expect(res.status).toBe(404);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

describe('apiJson', () => {
  it('parses JSON on success', async () => {
    mockFetch.mockResolvedValueOnce(makeRes('{"id":1}', 200));

    const data = await apiJson<{ id: number }>('/api/test');

    expect(data).toEqual({ id: 1 });
  });

  it('throws on non-ok status', async () => {
    mockFetch.mockResolvedValueOnce(makeRes('bad request', 400, 'Bad Request'));

    await expect(apiJson('/api/test')).rejects.toThrow('400 Bad Request: bad request');
  });
});
