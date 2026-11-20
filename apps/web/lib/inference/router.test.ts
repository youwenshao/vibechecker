import { describe, expect, it, vi } from "vitest";
import { events, routeInference, validSentences } from "./router";
import {
  digest,
  deviceIdentity,
  makeRetry,
  verifyRetry,
  verifyHeartbeat,
  signedHeaders,
} from "../server/security";

vi.stubEnv("PRIMARY_INFERENCE_URL", "https://primary.example");
vi.stubEnv("FALLBACK_INFERENCE_URL", "https://fallback.example");
vi.stubEnv("CF_ACCESS_CLIENT_ID", "primary-id");
vi.stubEnv("CF_ACCESS_CLIENT_SECRET", "primary-secret");
vi.stubEnv("INFERENCE_HMAC_SECRET", "a".repeat(32));
vi.stubEnv("CHECKS_SECRET", "b".repeat(32));
const ok = () =>
  new Response('{"type":"error","code":"busy","retryable":true}\n', {
    headers: { "Content-Type": "application/x-ndjson" },
  });
const options = () => ({
  lastSeen: new Date().toISOString(),
  forceFallback: false,
  signal: new AbortController().signal,
  headerTimeout: 20,
});

describe("upstream selection", () => {
  it.each(["busy", "down", "hung", "disconnect"])(
    "routes %s to Modal with a fresh signature",
    async (condition) => {
      const attempts: { url: string; headers: Headers }[] = [];
      const fetcher: typeof fetch = async (url, init) => {
        attempts.push({ url: String(url), headers: new Headers(init?.headers) });
        if (attempts.length === 2) return ok();
        if (condition === "disconnect") throw TypeError("connect");
        if (condition === "hung")
          return await new Promise((_, reject) =>
            init?.signal?.addEventListener("abort", () => reject(init.signal!.reason)),
          );
        return new Response(null, { status: condition === "down" ? 502 : 503 });
      };
      expect((await routeInference("hello", { ...options(), fetcher })).primary).toBe(false);
      expect(attempts.map((x) => new URL(x.url).hostname)).toEqual([
        "primary.example",
        "fallback.example",
      ]);
      expect(attempts[0]!.headers.get("x-vibe-id")).not.toEqual(
        attempts[1]!.headers.get("x-vibe-id"),
      );
      expect(attempts[0]!.headers.get("cf-access-client-id")).toBe("primary-id");
      expect(attempts[1]!.headers.get("cf-access-client-id")).toBeNull();
    },
  );
  it("uses primary only while its matching heartbeat is fresh", async () => {
    const fetcher = vi.fn(async () => ok());
    expect((await routeInference("hello", { ...options(), fetcher })).primary).toBe(true);
    for (const opts of [
      { lastSeen: undefined },
      { lastSeen: new Date(Date.now() - 181000).toISOString() },
      { forceFallback: true },
    ])
      expect((await routeInference("hello", { ...options(), ...opts, fetcher })).primary).toBe(
        false,
      );
    expect(fetcher).toHaveBeenCalledTimes(4);
  });
  it("rejects an unexpected success payload", async () => {
    const fetcher = vi.fn(async () => new Response("unexpected", { status: 200 }));
    await expect(routeInference("hello", { ...options(), fetcher })).rejects.toThrow();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

it("reassembles split NDJSON records and rejects additional content fields", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(c) {
      for (const part of [
        '{"type":"pro',
        'gress","stage":"quick","done":0,"total":1}\n',
        '{"type":"error","code":"busy","retryable":false,"text":"forbidden"}',
      ])
        c.enqueue(encoder.encode(part));
      c.close();
    },
  });
  const iter = events(stream);
  expect((await iter.next()).value).toMatchObject({ type: "progress" });
  await expect(iter.next()).rejects.toThrow();
});

it("binds retry grants to a device, canonical content key and expiry", () => {
  const device = deviceIdentity();
  expect(deviceIdentity(device.cookie).id).toBe(device.id);
  expect(deviceIdentity(device.cookie + "x").id).not.toBe(device.id);
  const key = digest("cache", "v1", "quick", "hello");
  const token = makeRetry(device.id, key);
  expect(verifyRetry(token, device.id, key)).toBeTruthy();
  expect(verifyRetry(token, "other", key)).toBeNull();
  expect(verifyRetry(token, device.id, "other")).toBeNull();
});

it("accepts the shared Python/Node signature vector and rejects a modified heartbeat", () => {
  const sample = signedHeaders(
    "POST",
    "/v1/analyze",
    "{}",
    "1700000000",
    "65bcd128-7849-487d-abc1-c1bab305f6ad",
  );
  expect(sample["x-vibe-signature"]).toBe(
    "ddf672268e1ea68c561d1184fbafcc9645cc6f58373096963a52efadf40914f4",
  );
  const body = '{"engineVersion":"v0"}';
  const req = new Request("https://example.com/api/engine/heartbeat", {
    headers: signedHeaders("POST", "/api/engine/heartbeat", body),
  });
  expect(verifyHeartbeat(req, body)).toBeTruthy();
  expect(verifyHeartbeat(req, body + " ")).toBeNull();
});

it("rejects overlaps, empty ranges, out-of-bounds or half-surrogate offsets before caching", () => {
  const text = "😀A.\r\nB.";
  const item = (start: number, end: number) => ({ start, end, score: .5, signals: [] });
  expect(validSentences(text, [item(0, 4), item(6, 8)])).toBe(true);
  for (const range of [item(1, 4), item(0, 1), item(3, 3), item(6, 9)]) {
    expect(validSentences(text, [range])).toBe(false);
  }
  expect(validSentences(text, [item(0, 4), item(3, 8)])).toBe(false);
  expect(validSentences(text, [item(3, 8)], 4)).toBe(false);
});
