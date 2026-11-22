import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { env } from "./security";

export async function authClient() {
  const jar = await cookies();
  return createServerClient(env("SUPABASE_URL"), env("SUPABASE_PUBLISHABLE_KEY"), {
    cookieOptions: {
      httpOnly: true,
      secure: process.env.APP_ORIGIN?.startsWith("https://"),
      sameSite: "lax",
      path: "/",
    },
    cookies: {
      getAll: () => jar.getAll(),
      setAll: (changed) => {
        for (const { name, value, options } of changed) jar.set(name, value, options);
      },
    },
  });
}

export async function viewer() {
  if (!process.env.SUPABASE_PUBLISHABLE_KEY) return null;
  const client = await authClient();
  const { data, error } = await client.auth.getUser();
  if (
    error &&
    error.name !== "AuthSessionMissingError" &&
    error.status !== 401 &&
    error.status !== 403
  )
    throw Error("Account unavailable");
  return data.user?.id ?? null;
}

export function privateJson(data: unknown, status = 200) {
  return NextResponse.json(data, { status, headers: { "cache-control": "private, no-store" } });
}
export function sameOrigin(req: Request) {
  return (
    req.headers.get("origin") === appOrigin(req) &&
    req.headers.get("content-type")?.split(";")[0] === "application/json"
  );
}
export function appOrigin(req: Request) {
  return new URL(process.env.APP_ORIGIN || req.url).origin;
}
