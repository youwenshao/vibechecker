import { z } from "zod";
import { reportServiceFailure } from "../../../lib/telemetry";
import { createClient } from "@supabase/supabase-js";
import { authClient, privateJson, sameOrigin, viewer } from "../../../lib/server/auth";
import { digest, env, readBody } from "../../../lib/server/security";
import { rest } from "../../../lib/server/store";
import { decryptEssay } from "../../../lib/server/envelope";

export async function GET(req: Request) {
  try {
    const owner = await viewer();
    if (!owner) return privateJson({ owner: null });
    const url = new URL(req.url);
    const before = url.searchParams.get("before");
    // The cursor includes the ID so equal expiry timestamps cannot skip a row.
    const cursor = before
      ? z.tuple([z.iso.datetime({ offset: true }), z.uuid()]).parse(JSON.parse(before))
      : null;
    const columns = "id,mode,word_count,engine_version,expires_at";
    const query = new URLSearchParams({
      select: columns,
      user_id: "eq." + owner,
      expires_at: "gt." + new Date().toISOString(),
      order: "expires_at.desc,id.desc",
      limit: "31",
    });
    if (cursor)
      query.set(
        "or",
        `(expires_at.lt.${cursor[0]},and(expires_at.eq.${cursor[0]},id.lt.${cursor[1]}))`,
      );
    const rows = await rest("checks?" + query);
    return privateJson({ owner, rows: rows.slice(0, 30), more: rows.length > 30 });
  } catch {
    await reportServiceFailure("history");
    return privateJson({}, 503);
  }
}

const Command = z.discriminatedUnion("action", [
  z.object({ action: z.literal("claim"), id: z.uuid(), token: z.string().regex(/^[\w-]{43}$/) }),
  z.object({ action: z.literal("read"), id: z.uuid() }),
  z.object({ action: z.literal("delete"), id: z.uuid() }),
  z.object({ action: z.enum(["deleteAll", "deleteAccount", "signOut"]) }),
]);
export async function POST(req: Request) {
  if (!sameOrigin(req)) return privateJson({}, 403);
  try {
    const owner = await viewer();
    if (!owner) return privateJson({}, 401);
    const parsed = Command.safeParse(JSON.parse(await readBody(req, 2048)));
    if (!parsed.success) return privateJson({}, 400);
    const cmd = parsed.data;
    if (cmd.action === "claim") {
      return privateJson({
        claimed: await rest("rpc/claim_check", {
          p_owner: owner,
          p_id: cmd.id,
          p_hash: digest("claim", cmd.token),
        }),
      });
    }
    const client = await authClient();
    if (cmd.action === "signOut") {
      const { error } = await client.auth.signOut({ scope: "local" });
      return privateJson({}, error ? 503 : 200);
    }
    if (cmd.action === "deleteAccount") {
      const admin = createClient(env("SUPABASE_URL"), env("SUPABASE_SERVICE_ROLE_KEY"), {
        auth: { autoRefreshToken: false, persistSession: false },
      });
      // Hard deletion cascades sessions and checks. Local logout also clears SSR cookies.
      const { error } = await admin.auth.admin.deleteUser(owner);
      if (error) return privateJson({}, 503);
      await client.auth.signOut({ scope: "local" });
      return privateJson({});
    }
    if (cmd.action === "read") {
      const rows = await rest(
        "checks?select=result,mode,engine_version&id=eq." +
          cmd.id +
          "&user_id=eq." +
          owner +
          "&expires_at=gt." +
          encodeURIComponent(new Date().toISOString()),
      );
      if (!rows.length) return privateJson({}, 404);
      const encrypted = await rest("rpc/read_saved_essay", { p_id: cmd.id, p_owner: owner });
      return privateJson({
        ...rows[0],
        text: encrypted ? decryptEssay(encrypted, cmd.id, owner) : null,
      });
    }
    let query = client.from("checks").delete().eq("user_id", owner);
    if (cmd.action === "delete") query = query.eq("id", cmd.id);
    const { error } = await query;
    return privateJson({}, error ? 503 : 200);
  } catch {
    return privateJson({}, 503);
  }
}
