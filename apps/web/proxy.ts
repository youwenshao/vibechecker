import { createServerClient } from "@supabase/ssr";
import createMiddleware from "next-intl/middleware";
import type { NextRequest } from "next/server";
import { routing } from "./i18n/routing";

const localize = createMiddleware(routing);
export default async function proxy(request: NextRequest) {
  let response = localize(request);
  const key = process.env.SUPABASE_PUBLISHABLE_KEY;
  if (key && process.env.SUPABASE_URL) {
    const client = createServerClient(process.env.SUPABASE_URL, key, {
      cookieOptions: {
        httpOnly: true,
        secure: request.nextUrl.protocol === "https:",
        sameSite: "lax",
        path: "/",
      },
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll(changes, headers) {
          for (const { name, value } of changes) request.cookies.set(name, value);
          response = localize(request);
          for (const { name, value, options } of changes)
            response.cookies.set(name, value, options);
          for (const [name, value] of Object.entries(headers)) response.headers.set(name, value);
        },
      },
    });
    await client.auth.getClaims();
  }
  return response;
}
export const config = { matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"] };
