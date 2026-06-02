import { NextRequest, NextResponse } from 'next/server';
import { isPublicPath } from '@/utils/auth-paths';

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (isPublicPath(pathname)) return NextResponse.next();

  const refreshToken = req.cookies.get('refresh_token')?.value;
  if (!refreshToken) {
    if (pathname.startsWith('/api/')) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    return NextResponse.redirect(new URL('/login', req.url));
  }

  return NextResponse.next();
}

// ⚠️ matcher 는 반드시 인라인 리터럴이어야 한다. Next.js 14 는 config.matcher 를
// 빌드 타임에 정적 분석하며, import 한 변수는 분석 불가로 "무시"한다 → matcher 가
// 사라져 미들웨어가 _next/static·favicon 까지 전 경로에서 실행되어 정적 자산이
// /login 으로 리다이렉트되고 페이지가 깨진다(#306 회귀). 값은 auth-paths.ts 의
// MIDDLEWARE_MATCHER 와 항상 동일하게 유지(테스트가 그 상수를 검증).
export const config = {
  matcher: ['/((?!_next/static|_next/image|images|favicon\\.ico).*)'],
};
