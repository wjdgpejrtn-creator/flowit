import { isPublicPath } from '../utils/auth-paths';

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
