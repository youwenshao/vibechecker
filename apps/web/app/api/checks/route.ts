import { randomBytes, randomUUID } from "node:crypto";
import { isIP } from "node:net";
import { after, NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { AnalyzeRequest, Backend, CheckResult, Version } from "@vibechecker/contracts";
import { events, routeInference, validScore } from "../../../lib/inference/router";
import {
  deviceIdentity,
  digest,
  env,
  makeRetry,
  readBody,
  verifyRetry,
  verifyTurnstile,
} from "../../../lib/server/security";
import {
  cached,
  consumeQuota,
  primaryHeartbeat,
  spendRetry,
  storeCheck,
  type Completed,
} from "../../../lib/server/store";

export const runtime = "nodejs";
export const maxDuration = 180;
const Submission = AnalyzeRequest.extend({
  turnstileToken: z.string().max(2048),
  retryToken: z.string().max(240).optional(),
});
const encoder = new TextEncoder();
function line(event: unknown) {
  return encoder.encode(JSON.stringify(event) + "\n");
}
function error(code: string, status: number) {
  return NextResponse.json({ code }, { status, headers: { "cache-control": "no-store" } });
}

export async function POST(req: NextRequest) {
  let data;
  try {
    const body = JSON.parse(await readBody(req, 800_512));
    data = Submission.parse(body);
  } catch (exc) {
    return error(
      exc instanceof RangeError ? "too_long" : "invalid_request",
      exc instanceof RangeError ? 413 : 400,
    );
  }

  const { text, turnstileToken, retryToken } = data;
  try {
    const version = Version.parse(env("ENGINE_VERSION"));
    const key = digest("cache", version, "quick", text.replace(/\r\n?/g, "\n").normalize("NFC"));
    const device = deviceIdentity(req.cookies.get("vc_device")?.value);
    // Vercel overwrites this header at ingress. Local requests share a development ceiling.
    const forwarded = process.env.VERCEL
      ? req.headers.get("x-vercel-forwarded-for")?.split(",")[0]?.trim()
      : undefined;
    const ip = forwarded && isIP(forwarded) ? forwarded : "unknown";
    if (retryToken) {
      const nonce = verifyRetry(retryToken, device.id, key);
      if (!nonce || !(await spendRetry(nonce))) return error("invalid_retry", 403);
    } else {
      if (!turnstileToken || !(await verifyTurnstile(turnstileToken, ip)))
        return error("turnstile", 403);
      if (!(await consumeQuota(digest("quota", device.id), digest("ip", ip))))
        return error("quota", 429);
    }
    const checkId = randomUUID();
    const claimToken = randomBytes(32).toString("base64url");
    let completed: Completed | undefined;
    const finish = (backend: Backend, result: CheckResult) => {
      completed = {
        id: checkId,
        key,
        claimHash: digest("claim", claimToken),
        version,
        backend,
        result,
      };
      return line({ type: "result", result, checkId, claimToken, backend, engineVersion: version });
    };
    const found = await cached(key);
    let stream: Uint8Array | ReadableStream<Uint8Array>;
    if (found) {
      const result = CheckResult.parse(found.result);
      if (!validScore(result)) return error("internal", 503);
      stream = finish(Backend.parse(found.backend), result);
    } else {
      const abort = new AbortController();
      const { response, primary } = await routeInference(text, {
        forceFallback: Boolean(retryToken),
        lastSeen: retryToken ? undefined : await primaryHeartbeat(version),
        signal: AbortSignal.any([req.signal, abort.signal]),
      });
      const retryable = primary && !retryToken;
      function failure() {
        return line({
          type: "error",
          code: "internal",
          retryable,
          ...(retryable ? { retryToken: makeRetry(device.id, key) } : {}),
        });
      }
      async function* relay() {
        let backend: Backend | undefined;
        try {
          for await (const event of events(response.body!)) {
            if (event.type === "accepted" && !backend && event.engineVersion === version) {
              backend = event.backend;
              yield line(event);
            } else if (event.type === "error") {
              yield event.retryable ? failure() : line(event);
              return;
            } else if (event.type === "result" && backend) {
              yield finish(backend, event.result);
              return;
            } else if (event.type === "progress" && backend) {
              yield line(event);
            } else throw Error("Unexpected inference event");
          }
        } catch {
          /* A truncated or invalid response uses the same retry path. */
        }
        yield failure();
      }
      const iterator = relay();
      stream = new ReadableStream({
        async pull(controller) {
          const next = await iterator.next();
          if (next.done) controller.close();
          else controller.enqueue(next.value);
        },
        async cancel() {
          abort.abort();
          await iterator.return(undefined);
        },
      });
    }
    after(async () => {
      if (completed) await storeCheck(completed);
    });
    const res = new NextResponse(stream instanceof Uint8Array ? Buffer.from(stream) : stream, {
      headers: {
        "content-type": "application/x-ndjson",
        "cache-control": "private, no-store",
        "x-content-type-options": "nosniff",
      },
    });
    res.cookies.set("vc_device", device.cookie, {
      httpOnly: true,
      secure: req.nextUrl.protocol === "https:",
      sameSite: "lax",
      path: "/",
      maxAge: 86400 * 365,
    });
    return res;
  } catch {
    // Outbound errors and malformed upstream payloads must never echo request content.
    return error("busy", 503);
  }
}
