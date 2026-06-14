import type { NextRequest } from 'next/server';

// 스킬 추출 2차(detail) 전용 프록시 (REQ-010/013, 위저드 #353 metadata/detail 분리).
//
// 왜 next.config rewrite가 아니라 Route Handler인가:
//   detail은 토큰 무거운 Gemma structured(JSON 강제) 추출이라 30~60s 걸리는 long POST다.
//   `/api/:path*` rewrite(Next 내장 프록시)로 이 긴 요청을 프록시하면 응답 전에 업스트림
//   소켓이 끊겨(`Error: socket hang up`) Next가 500(HTML)을 내려보낸다 — api_server는 실제로
//   200으로 완료하는데 프론트가 먼저 끊긴다(2026-06-14 staging 실측: frontend 500 8건 vs
//   api 200 8건). SSE가 아니어도 long POST는 rewrite로 못 버틴다(extract SSE와 동류 결함).
//   Route Handler에서 직접 fetch하면 응답 수신까지 연결을 유지한다. 같은 출처(/api)라 SSO
//   HttpOnly 쿠키 인증도 그대로 전달된다.
//
// filesystem route는 rewrite보다 우선하므로 이 경로(POST /api/v1/skills/extract/detail)만
// rewrite를 우회하고 나머지 /api/* 는 기존 rewrite를 그대로 탄다.

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// 빌드 ARG → Dockerfile ENV로 런타임 노출됨(프론트 컨테이너). rewrite와 동일 타깃.
const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

export async function POST(req: NextRequest): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${API_PROXY_TARGET}/api/v1/skills/extract/detail`, {
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
    // upstream(api) 다운/소켓 끊김 — 핸들러 throw 시 Next 500(HTML)이 내려가므로,
    // 프론트 client(apiJson)가 읽을 수 있는 JSON 502로 정돈한다(!res.ok→detail 텍스트 throw).
    const message = err instanceof Error ? err.message : 'upstream fetch failed';
    return new Response(
      JSON.stringify({ detail: `Skills extract detail upstream 연결 실패: ${message}` }),
      { status: 502, headers: { 'Content-Type': 'application/json' } },
    );
  }

  // detail은 단건 JSON 응답 — upstream status·content-type을 그대로 전달.
  const headers = new Headers();
  headers.set('Content-Type', upstream.headers.get('content-type') ?? 'application/json');
  headers.set('Cache-Control', 'no-store');
  return new Response(upstream.body, { status: upstream.status, headers });
}
