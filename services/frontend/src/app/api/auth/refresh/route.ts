import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL ?? 'http://localhost:8000';
const ACCESS_MAX_AGE = 60 * 60;            // 1시간
const REFRESH_MAX_AGE = 60 * 60 * 24 * 30; // 30일

export async function POST(req: NextRequest) {
  const refreshToken = req.cookies.get('refresh_token')?.value;
  if (!refreshToken) {
    return NextResponse.json({ error: 'No refresh token' }, { status: 401 });
  }

  const backendRes = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!backendRes.ok) {
    const r = NextResponse.json({ error: 'Refresh failed' }, { status: 401 });
    r.cookies.delete('access_token');
    r.cookies.delete('refresh_token');
    return r;
  }

  const data = await backendRes.json() as { access_token: string; refresh_token: string };
  const res = NextResponse.json({ ok: true });
  res.cookies.set('access_token', data.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: ACCESS_MAX_AGE,
    path: '/',
  });
  res.cookies.set('refresh_token', data.refresh_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: REFRESH_MAX_AGE,
    path: '/',
  });
  return res;
}
