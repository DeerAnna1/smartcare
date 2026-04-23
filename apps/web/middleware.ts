import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_COOKIE_KEY = "medhelp_token";

const protectedPrefixes = [
  "/chat",
  "/conclusion",
  "/event-confirm",
  "/execution",
  "/records",
  "/health-records",
  "/skills",
  "/iot-simulator",
];

function isProtectedPath(pathname: string) {
  return protectedPrefixes.some((prefix) => pathname.startsWith(prefix));
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (!isProtectedPath(pathname)) {
    return NextResponse.next();
  }

  const token = request.cookies.get(AUTH_COOKIE_KEY)?.value;
  if (token) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/auth", request.url);
  loginUrl.searchParams.set("redirect", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    "/chat/:path*",
    "/conclusion/:path*",
    "/event-confirm/:path*",
    "/execution/:path*",
    "/records/:path*",
    "/health-records/:path*",
    "/skills/:path*",
    "/iot-simulator/:path*",
  ],
};
