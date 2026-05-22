export const PUBLIC_PATHS = ['/login', '/api/v1/auth'];

export const isPublicPath = (pathname: string) =>
  PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p + '?'),
  );
