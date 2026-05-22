import { isPublicPath } from '../utils/auth-paths';

describe('middleware PUBLIC_PATHS matching', () => {
  it.each([
    ['/login',           true],
    ['/login?next=%2F',  true],
    ['/api/auth',        true],
    ['/api/auth/token',  true],
  ])('%s → public', (path, expected) => {
    expect(isPublicPath(path)).toBe(expected);
  });

  it.each([
    ['/'],
    ['/admin'],
    ['/admin/credentials'],
    ['/workflows'],
    ['/api/workflows'],
  ])('%s → protected', (path) => {
    expect(isPublicPath(path)).toBe(false);
  });
});
