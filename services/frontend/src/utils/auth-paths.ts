export const PUBLIC_PATHS = ['/login', '/api/auth'];

export const isPublicPath = (pathname: string) =>
  PUBLIC_PATHS.some((p) => pathname.startsWith(p));
