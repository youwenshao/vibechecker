import { Version } from "@vibechecker/contracts";
import { z } from "zod";
import { readBody, verifyHeartbeat } from "../../../../lib/server/security";
import { heartbeat } from "../../../../lib/server/store";

export async function POST(req: Request) {
  try {
    const body = await readBody(req, 1024);
    const time = verifyHeartbeat(req, body);
    if (time === null) return new Response(null, { status: 403 });
    const { engineVersion } = z.strictObject({ engineVersion: Version }).parse(JSON.parse(body));
    await heartbeat(engineVersion, time);
    return new Response(null, { status: 204 });
  } catch (e) {
    return new Response(null, {
      status:
        e instanceof RangeError
          ? 413
          : e instanceof z.ZodError || e instanceof SyntaxError
            ? 400
            : 503,
    });
  }
}
