import type { NextRequest } from 'next/server';

// AI 워크플로우 생성(compose) SSE 전용 프록시 (REQ-004/010).
//
// 왜 next.config rewrite가 아니라 Route Handler인가:
//   `/api/:path*` rewrite로 compose SSE를 프록시하면 composer drafter LLM이 50~70초
//   무프레임으로 도는 동안 rewrite 프록시(Next node)가 upstream(api_server) 연결을
//   유지하지 못하고 끊는다 — staging 실측: 노드 검색(~12s 무음) 구간에서 프록시가
//   `socket hang up (ECONNRESET)` → 브라우저에 500. (skills/extract와 동일 함정.)
//   Route Handler에서 `new Response(upstream.body)`로 직접 파이프하면 upstream 스트림이
//   끊김 없이 브라우저로 전파된다. orchestrator의 15s heartbeat와 함께 연결을 살린다.
//   같은 출처(/api) 유지라 SSO HttpOnly 쿠키 인증도 그대로.
//
// filesystem route는 rewrite보다 우선하므로 이 경로(POST /api/v1/agents/sessions)만
// rewrite를 우회하고 나머지 /api/* 는 기존 rewrite를 그대로 탄다.

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// 빌드 ARG → Dockerfile ENV로 런타임 노출됨(프론트 컨테이너). rewrite와 동일 타깃.
const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

export async function POST(req: NextRequest): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${API_PROXY_TARGET}/api/v1/agents/sessions`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        // SSO HttpOnly 쿠키 전달 — 동일 출처라 브라우저가 Next로 보낸 쿠키를 api로 전달.
        cookie: req.headers.get('cookie') ?? '',
      },
      body: await req.text(),
      cache: 'no-store',
    });
  } catch (err) {
    // upstream(api) 다운/네트워크 오류 — 핸들러 throw 시 Next 500(HTML)이 내려가므로,
    // 프론트 client가 읽을 수 있는 JSON 502로 정돈(streamCreateSession이 !res.ok→텍스트 throw).
    const message = err instanceof Error ? err.message : 'upstream fetch failed';
    return new Response(JSON.stringify({ detail: `compose upstream 연결 실패: ${message}` }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // 성공(SSE)이든 에러(JSON)든 upstream의 status·content-type을 그대로 전달.
  // body는 ReadableStream을 직접 파이프 → upstream이 닫으면 브라우저 reader도 즉시 done.
  const headers = new Headers();
  headers.set(
    'Content-Type',
    upstream.headers.get('content-type') ?? 'text/event-stream',
  );
  // SSE 스트리밍 보장 — LB/프록시 버퍼링 차단(repo 표준 SSE_HEADERS와 일관).
  headers.set('Cache-Control', 'no-cache, no-transform');
  headers.set('X-Accel-Buffering', 'no');
  headers.set('Connection', 'keep-alive');

  return new Response(upstream.body, { status: upstream.status, headers });
}
