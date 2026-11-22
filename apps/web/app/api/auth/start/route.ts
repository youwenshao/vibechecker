import { z } from "zod";
import { reportServiceFailure } from "../../../../lib/telemetry";
import { appOrigin, authClient, privateJson, sameOrigin } from "../../../../lib/server/auth";
import { readBody, verifyTurnstile } from "../../../../lib/server/security";

const Form = z
  .discriminatedUnion("provider", [
    z.object({ provider: z.literal("email"), email: z.email().max(320) }),
    z.object({ provider: z.literal("google") }),
  ])
  .and(z.object({ locale: z.enum(["en", "zh-HK"]), token: z.string().min(1).max(2048) }));

export async function POST(req: Request) {
  if (!sameOrigin(req)) return privateJson({}, 403);
  try {
    const form = Form.safeParse(JSON.parse(await readBody(req, 4096)));
    if (!form.success) return privateJson({}, 400);
    const data = form.data;
    const redirectTo = new URL("/api/auth/callback?locale=" + data.locale, appOrigin(req)).href;
    const client = await authClient();
    if (data.provider === "email") {
      // Supabase consumes this single-use token when project CAPTCHA protection is enabled.
      const { error } = await client.auth.signInWithOtp({
        email: data.email,
        options: { captchaToken: data.token, emailRedirectTo: redirectTo },
      });
      return privateJson({}, error ? 400 : 200);
    }
    if (!(await verifyTurnstile(data.token, "unknown", "auth"))) return privateJson({}, 403);
    const { data: oauth, error } = await client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo, skipBrowserRedirect: true },
    });
    return error ? privateJson({}, 400) : privateJson({ url: oauth.url });
  } catch {
    await reportServiceFailure("sign-in");
    return privateJson({}, 503);
  }
}
