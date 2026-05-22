import { isPublicPath } from '../utils/auth-paths';

describe('middleware PUBLIC_PATHS matching', () => {
  it.each([
    ['/login',              true],
    ['/login?next=%2F',     true],
    ['/api/auth',           true],
    ['/api/auth/token',     true],
    ['/api/auth/refresh',   true],
    ['/api/auth/logout',    true],
  ])('%s → public', (path, expected) => {
    expect(isPublicPath(path)).toBe(expected);
  });

  it.each([
    ['/'],
    ['/admin'],
    ['/admin/credentials'],
    ['/workflows'],
    ['/api/workflows'],
    ['/auth/callback'],
    ['/auth/callback?code=abc&state=xyz'],
  ])('%s → protected', (path) => {
    expect(isPublicPath(path)).toBe(false);
  });
});
