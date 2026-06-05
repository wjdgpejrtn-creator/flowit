import type { NextRequest } from 'next/server';

// two-shot 2차(스킬 선택/건너뛰기) SSE 프록시 (REQ-013).
//
// compose(POST /agents/sessions)와 동일하게 round=2 응답도 SSE(drafter→…→result)라
// next.config rewrite로 프록시하면 무음 구간에 연결이 끊긴다(ECONNRESET). Route Handler에서
// upstream.body 직접 파이프로 우회. SSO 쿠키 passthrough 유지.

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

export async function POST(
  req: NextRequest,
  { params }: { params: { session_id: string } },
): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(
      `${API_PROXY_TARGET}/api/v1/agents/sessions/${params.session_id}/slot`,
      {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          cookie: req.headers.get('cookie') ?? '',
        },
        body: await req.text(),
        cache: 'no-store',
      },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : 'upstream fetch failed';
    return new Response(JSON.stringify({ detail: `slot upstream 연결 실패: ${message}` }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const headers = new Headers();
  headers.set(
    'Content-Type',
    upstream.headers.get('content-type') ?? 'text/event-stream',
  );
  headers.set('Cache-Control', 'no-cache, no-transform');
  headers.set('X-Accel-Buffering', 'no');
  headers.set('Connection', 'keep-alive');

  return new Response(upstream.body, { status: upstream.status, headers });
}
