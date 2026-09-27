import { NextResponse, type NextRequest } from "next/server";
import {
  COOKIE_NAME,
  THIRTY_DAYS_MS,
  getCookieSecret,
  verifySession,
} from "@/lib/editorAuth";

export const config = {
  matcher: ["/editor/:path*"],
};

export async function middleware(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;

  if (!pathname.startsWith("/editor/")) {
    return NextResponse.next();
  }

  if (pathname === "/editor/login") {
    return NextResponse.next();
  }

  const secret = getCookieSecret();
  const cookieValue = request.cookies.get(COOKIE_NAME)?.value;

  const isAuthenticated =
    secret !== undefined &&
    cookieValue !== undefined &&
    (await verifySession(secret, cookieValue, Date.now(), THIRTY_DAYS_MS));

  if (isAuthenticated) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/editor/login", request.url);
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}
