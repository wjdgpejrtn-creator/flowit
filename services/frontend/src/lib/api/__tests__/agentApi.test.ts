import { TextDecoder as NodeTextDecoder } from 'util';

// @ts-expect-error jsdom lacks TextDecoder
global.TextDecoder = NodeTextDecoder;

import { streamCreateSession } from '../agentApi';

jest.mock('../../apiClient', () => ({
  apiFetch: jest.fn(),
}));

import { apiFetch } from '../../apiClient';
const mockApiFetch = apiFetch as jest.MockedFunction<typeof apiFetch>;

function mockReader(chunks: string[]) {
  let i = 0;
  return {
    read: jest.fn().mockImplementation(() => {
      if (i < chunks.length) {
        const value = Buffer.from(chunks[i], 'utf-8');
        i++;
        return Promise.resolve({ done: false, value });
      }
      return Promise.resolve({ done: true, value: undefined });
    }),
    releaseLock: jest.fn(),
  };
}

function mockResponse(chunks: string[], status = 200): Partial<Response> {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    body: { getReader: () => mockReader(chunks) } as unknown as ReadableStream,
    text: () => Promise.resolve(chunks.join('')),
  };
}

function framesToSSE(frames: Record<string, unknown>[]): string {
  return frames.map((f) => `data: ${JSON.stringify(f)}\n\n`).join('');
}

beforeEach(() => mockApiFetch.mockReset());

describe('streamCreateSession', () => {
  it('session frame을 올바르게 파싱한다', async () => {
    const frames: Record<string, unknown>[] = [];
    mockApiFetch.mockResolvedValueOnce(
      mockResponse([framesToSSE([{ frame_type: 'session', session_id: 'sid-1', langgraph_thread_id: 'tid-1' }])]) as Response,
    );

    await streamCreateSession({ message: '테스트' }, (f) => frames.push(f));

    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ frame_type: 'session', session_id: 'sid-1', langgraph_thread_id: 'tid-1' });
  });

  it('여러 frame을 순서대로 전달한다', async () => {
    const frames: Record<string, unknown>[] = [];
    mockApiFetch.mockResolvedValueOnce(
      mockResponse([framesToSSE([
        { frame_type: 'session', session_id: 'sid-1' },
        { frame_type: 'agent_node', agent_node_name: 'security' },
        { frame_type: 'agent_node', agent_node_name: 'intent' },
        { frame_type: 'result', intent: 'create_workflow', payload: { status: 'ready_to_execute', workflow_id: 'wf-1', message: '완료' } },
      ])]) as Response,
    );

    await streamCreateSession({ message: '테스트' }, (f) => frames.push(f));

    expect(frames).toHaveLength(4);
    expect(frames.map((f) => f.frame_type)).toEqual(['session', 'agent_node', 'agent_node', 'result']);
    expect(frames[1].agent_node_name).toBe('security');
    expect(frames[2].agent_node_name).toBe('intent');
  });

  it('청크가 분할된 SSE도 정상 파싱한다', async () => {
    const frames: Record<string, unknown>[] = [];
    const frame1 = JSON.stringify({ frame_type: 'session', session_id: 'sid-1' });
    const frame2 = JSON.stringify({ frame_type: 'agent_node', agent_node_name: 'security' });
    mockApiFetch.mockResolvedValueOnce(
      mockResponse([
        `data: ${frame1}\n`,
        `\ndata: ${frame2}\n\n`,
      ]) as Response,
    );

    await streamCreateSession({ message: '테스트' }, (f) => frames.push(f));

    expect(frames).toHaveLength(2);
    expect(frames[0].frame_type).toBe('session');
    expect(frames[1].frame_type).toBe('agent_node');
  });

  it('비정상 응답(non-ok)은 에러를 throw한다', async () => {
    mockApiFetch.mockResolvedValueOnce(
      mockResponse(['Unauthorized'], 401) as Response,
    );

    await expect(
      streamCreateSession({ message: '테스트' }, () => {}),
    ).rejects.toThrow('401');
  });

  it('malformed JSON frame은 무시하고 나머지를 처리한다', async () => {
    const frames: Record<string, unknown>[] = [];
    const text = `data: {invalid json}\n\ndata: ${JSON.stringify({ frame_type: 'session', session_id: 'ok' })}\n\n`;
    mockApiFetch.mockResolvedValueOnce(mockResponse([text]) as Response);

    await streamCreateSession({ message: '테스트' }, (f) => frames.push(f));

    expect(frames).toHaveLength(1);
    expect(frames[0].session_id).toBe('ok');
  });

  it('session_id가 있으면 요청에 포함한다', async () => {
    mockApiFetch.mockResolvedValueOnce(mockResponse([]) as Response);

    await streamCreateSession({ message: '테스트', session_id: 'existing' }, () => {});

    expect(mockApiFetch).toHaveBeenCalledWith('/api/v1/agents/sessions', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ message: '테스트', session_id: 'existing' }),
    }));
  });

  it('error frame을 올바르게 전달한다', async () => {
    const frames: Record<string, unknown>[] = [];
    mockApiFetch.mockResolvedValueOnce(
      mockResponse([framesToSSE([{ frame_type: 'error', code: 'E_PROXY', message: '연결 실패' }])]) as Response,
    );

    await streamCreateSession({ message: '테스트' }, (f) => frames.push(f));

    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ frame_type: 'error', code: 'E_PROXY', message: '연결 실패' });
  });
});
