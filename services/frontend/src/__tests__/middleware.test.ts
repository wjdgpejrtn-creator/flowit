import { isPublicPath, MIDDLEWARE_MATCHER } from '../utils/auth-paths';

describe('middleware PUBLIC_PATHS matching', () => {
  it.each([
    ['/login',                 true],
    ['/login?next=%2F',        true],
    ['/api/v1/auth',           true],
    ['/api/v1/auth/authorize', true],
    ['/api/v1/auth/callback',  true],
    ['/api/v1/auth/refresh',   true],
    ['/api/v1/auth/logout',    true],
  ])('%s → public', (path, expected) => {
    expect(isPublicPath(path)).toBe(expected);
  });

  it.each([
    ['/'],
    ['/admin'],
    ['/admin/credentials'],
    ['/workflows'],
    ['/api/workflows'],
    ['/api/auth'],
    ['/api/auth/refresh'],
    ['/auth/callback'],
    ['/auth/callback?code=abc&state=xyz'],
  ])('%s → protected', (path) => {
    expect(isPublicPath(path)).toBe(false);
  });
});

describe('middleware matcher — 정적 자산은 인증 게이트 우회', () => {
  // matcher 에 매치되면 미들웨어가 실행되어 인증 검사 → 미인증 시 /login 리다이렉트.
  // 정적 자산은 매치되면 안 된다(매치 시 로그인 페이지에서 이미지가 깨짐).
  const runsMiddleware = (pathname: string) =>
    MIDDLEWARE_MATCHER.some((m) => new RegExp(`^${m}$`).test(pathname));

  it.each([
    ['/images/flowit-logo-v2.png'],
    ['/images/idcard-badge.png'],
    ['/images/flowit-wordmark-v2.png'],
    ['/_next/static/chunk.js'],
    ['/favicon.ico'],
  ])('%s → 미들웨어 우회', (path) => {
    expect(runsMiddleware(path)).toBe(false);
  });

  it.each([['/login'], ['/workflows'], ['/admin']])('%s → 미들웨어 실행', (path) => {
    expect(runsMiddleware(path)).toBe(true);
  });
});
