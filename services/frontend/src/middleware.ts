import { NextRequest, NextResponse } from 'next/server';
import { isPublicPath, MIDDLEWARE_MATCHER } from '@/utils/auth-paths';

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

export const config = {
  matcher: MIDDLEWARE_MATCHER,
};
