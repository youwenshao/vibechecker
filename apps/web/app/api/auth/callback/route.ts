import { NextResponse } from "next/server";
import { appOrigin, authClient } from "../../../../lib/server/auth";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const locale = url.searchParams.get("locale") === "zh-HK" ? "zh-HK" : "en";
  let success = false;
  try {
    const code = url.searchParams.get("code");
    const flowId = url.searchParams.get("sb_flow_id") ?? undefined;
    if (code)
      success = !(await (await authClient()).auth.exchangeCodeForSession(code, { flowId })).error;
  } catch {
    /* A stale or previously used link returns to the sign-in form. */
  }
  const response = NextResponse.redirect(
    new URL("/" + locale + "/history" + (success ? "" : "?auth=failed"), appOrigin(req)),
  );
  response.headers.set("cache-control", "private, no-store");
  response.headers.set("referrer-policy", "no-referrer");
  return response;
}
