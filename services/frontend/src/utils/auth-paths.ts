export const PUBLIC_PATHS = ['/login', '/api/v1/auth'];

/**
 * 미들웨어 matcher 패턴. 매치되는 경로에서만 미들웨어(인증 검사)가 실행된다.
 * 정적 자산(_next/static·_next/image·images·favicon)은 제외 — 미인증 상태인
 * 로그인 페이지가 /images/*.png 를 요청할 때 /login 리다이렉트로 깨지던 문제 방지.
 * next 런타임에 의존하지 않도록 여기(util)에 정의해 테스트에서 직접 검증 가능하게 둔다.
 */
export const MIDDLEWARE_MATCHER = ['/((?!_next/static|_next/image|images|favicon\\.ico).*)'];

export const isPublicPath = (pathname: string) =>
  PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p + '?'),
  );
