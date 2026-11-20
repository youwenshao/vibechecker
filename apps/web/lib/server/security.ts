import { createHash, createHmac, randomUUID, timingSafeEqual } from "node:crypto";

export function env(name: string): string {
  const value = process.env[name];
  if (!value) throw Error(`Missing ${name}`);
  return value;
}

function secret(name: string) {
  const key = env(name);
  if (Buffer.byteLength(key) < 32) throw Error(`Short ${name}`);
  return key;
}

export function equal(a: string, b: string): boolean {
  const x = Buffer.from(a),
    y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export function digest(...parts: string[]) {
  return createHmac("sha256", secret("CHECKS_SECRET")).update(JSON.stringify(parts)).digest("hex");
}

export function signedHeaders(
  method: string,
  path: string,
  body: string,
  timestamp = String(Math.floor(Date.now() / 1000)),
  id: string = randomUUID(),
) {
  const hash = createHash("sha256").update(body).digest("hex");
  const signature = createHmac("sha256", secret("INFERENCE_HMAC_SECRET"))
    .update([method, path, timestamp, id, hash].join("\n"))
    .digest("hex");
  return { "x-vibe-time": timestamp, "x-vibe-id": id, "x-vibe-signature": signature };
}

export function verifyHeartbeat(req: Request, body: string): number | null {
  const time = req.headers.get("x-vibe-time") ?? "";
  const nonce = req.headers.get("x-vibe-id") ?? "";
  if (
    !/^\d{10}$/.test(time) ||
    !/^[\da-f-]{36}$/.test(nonce) ||
    Math.abs(Date.now() / 1000 - Number(time)) > 60
  )
    return null;
  const expected = signedHeaders("POST", "/api/engine/heartbeat", body, time, nonce);
  return equal(req.headers.get("x-vibe-signature") ?? "", expected["x-vibe-signature"])
    ? Number(time)
    : null;
}

export function deviceIdentity(cookie?: string) {
  const [id, mac] = (cookie ?? "").split(".");
  const valid = /^[\da-f-]{36}$/.test(id ?? "") && equal(mac ?? "", digest("device", id!));
  const uuid = valid ? id! : randomUUID();
  return { id: uuid, cookie: `${uuid}.${digest("device", uuid)}` };
}

export function makeRetry(device: string, key: string) {
  const expiration = String(Math.floor(Date.now() / 1000) + 120);
  const id = randomUUID();
  return [expiration, id, digest("retry", device, key, expiration, id)].join(".");
}

export function verifyRetry(token: string, device: string, key: string): string | null {
  const [exp, id, mac, ...extra] = token.split(".");
  if (
    !exp ||
    !id ||
    !mac ||
    extra.length ||
    !/^\d{10}$/.test(exp) ||
    Number(exp) < Date.now() / 1000
  )
    return null;
  return equal(mac, digest("retry", device, key, exp, id)) ? digest("spent", id) : null;
}

export async function readBody(req: Request, max: number) {
  if (Number(req.headers.get("content-length")) > max) throw new RangeError();
  const reader = req.body?.getReader();
  if (!reader) return "";
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > max) {
        await reader.cancel();
        throw new RangeError();
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  return new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks));
}

export async function verifyTurnstile(token: string, ip: string) {
  const override = process.env.TURNSTILE_VERIFY_URL;
  if (
    override &&
    (process.env.VERCEL ||
      !["localhost", "127.0.0.1", "[::1]"].includes(new URL(override).hostname))
  )
    throw Error("Invalid verification endpoint");
  const hosts = env("TURNSTILE_HOSTNAMES")
    .split(",")
    .map((host) => host.trim());
  const params = new URLSearchParams({ secret: env("TURNSTILE_SECRET"), response: token });
  if (ip !== "unknown") params.set("remoteip", ip);
  const response = await fetch(
    override || "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    {
      method: "POST",
      body: params,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(8000),
    },
  );
  if (!response.ok) throw Error("Verification unavailable");
  const result = await response.json();
  return (
    result.success === true && result.action === "quick_check" && hosts.includes(result.hostname)
  );
}
