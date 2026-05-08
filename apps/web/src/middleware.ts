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
    const response = NextResponse.next();
    response.headers.set("x-middleware-ran", "true");
    return response;
  }

  const token = request.cookies.get(AUTH_COOKIE_KEY)?.value;
  if (token) {
    const response = NextResponse.next();
    response.headers.set("x-middleware-ran", "true");
    return response;
  }

  const loginUrl = new URL("/auth", request.url);
  loginUrl.searchParams.set("redirect", pathname);
  const response = NextResponse.redirect(loginUrl);
  response.headers.set("x-middleware-ran", "true");
  return response;
}

export const config = {
  matcher: [
    "/((?!api|_next|_static|favicon\\.ico|fonts|icons).*)",
  ],
};
