// Use a public fixture. Only numerical results and timings belong in verification records.
import { createHash, createHmac, randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { InferenceEvent } from "../packages/contracts/src/inference.ts";

const { values, positionals } = parseArgs({
  options: { target: { type: "string", default: "primary" } },
  allowPositionals: true,
});
const [input, runs = "1"] = positionals;
if (!["primary", "fallback"].includes(values.target) || positionals.length > 2)
  throw Error("Usage: probe-inference.mjs [--target primary|fallback] [public-essay.txt] [runs]");
const count = Number(runs);
if (!Number.isInteger(count) || count < 1 || count > 100) throw Error("Choose 1 to 100 probes");

const primary = values.target === "primary";
const backend = primary ? "mlx-metal" : "mlx-cuda";
const base = process.env[primary ? "PRIMARY_INFERENCE_URL" : "FALLBACK_INFERENCE_URL"];
const version = process.env.ENGINE_VERSION;
if (!base || !version) throw Error("Set the target URL and ENGINE_VERSION before the probe");

const path = input ? "/v1/analyze" : "/v1/health";
const method = input ? "POST" : "GET";
const body = input ? JSON.stringify({ mode: "quick", text: readFileSync(input, "utf8") }) : "";
const hash = createHash("sha256").update(body).digest("hex");
const url = new URL(path, base);
const latencies = [];

for (let i = 0; i < count; i++) {
  const stamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomUUID();
  const mac = createHmac("sha256", process.env.INFERENCE_HMAC_SECRET)
    .update([method, path, stamp, nonce, hash].join("\n")).digest("hex");
  const headers = {
    "content-type": "application/json", "x-vibe-time": stamp, "x-vibe-id": nonce, "x-vibe-signature": mac,
  };
  // Only the tunnel accepts the Cloudflare service token. Modal authenticates via HMAC.
  if (primary) {
    headers["CF-Access-Client-Id"] = process.env.CF_ACCESS_CLIENT_ID;
    headers["CF-Access-Client-Secret"] = process.env.CF_ACCESS_CLIENT_SECRET;
  }
  const start = performance.now();
  const r = await fetch(url, {
    method, body: input ? body : undefined, headers, redirect: "error", signal: AbortSignal.timeout(90000),
  });
  if (!r.ok) throw Error("Inference HTTP " + r.status);
  if (!input) {
    const health = await r.json();
    if (health.backend !== backend || health.engineVersion !== version) throw Error("Unexpected engine identity");
    console.log({ backend, version });
    break;
  }
  const events = (await r.text()).trim().split("\n").map(line => InferenceEvent.parse(JSON.parse(line)));
  const accepted = events[0];
  if (accepted.type !== "accepted" || accepted.backend !== backend || accepted.engineVersion !== version)
    throw Error("Unexpected engine identity");
  const last = events.at(-1);
  if (last.type !== "result") throw Error("Missing inference result");
  latencies.push(Math.round(performance.now() - start));
  if (i === 0) {
    const { wordCount, index, interval, signals } = last.result;
    console.log({ backend, version, words: wordCount, index, interval, signals: signals.length });
  }
}
if (latencies.length) {
  latencies.sort((a, b) => a - b);
  console.log({ runs: count, p50_ms: latencies[Math.ceil(0.5 * count) - 1], p95_ms: latencies[Math.ceil(0.95 * count) - 1] });
}
