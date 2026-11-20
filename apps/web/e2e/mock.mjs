import { createServer } from "node:http";

const engineVersion = "e2e-quick";
const stored = new Map();
const cache = new Map();
const result = {
  index: 62, interval: { low: 48, high: 75 }, band: "mixed", wordCount: 180,
  signals: [
    { id: "e1", value: 18.8, humanReference: 25.3 },
    { id: "e2", value: 2.46, humanReference: 2.9 },
    { id: "e6", value: 0.65, humanReference: 0.21 },
    { id: "stylometry", value: 0.46, humanReference: 0.39 },
  ], flags: [],
};

createServer(async (req, res) => {
  const { pathname, searchParams } = new URL(req.url, "http://127.0.0.1");
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString();
  if (pathname.endsWith("/v1/analyze")) {
    const { text } = JSON.parse(raw);
    const event = (value) => res.write(JSON.stringify(value) + "\n");
    res.writeHead(200, { "Content-Type": "application/x-ndjson" });
    const primary = Boolean(req.headers["cf-access-client-id"]);
    event({ type: "accepted", engineVersion, chunks: 1, backend: primary ? "mlx-metal" : "mlx-cuda" });
    if (text.startsWith("Failover") && primary) return res.end();
    event({ type: "progress", stage: "scoring", done: 1, total: 1 });
    if (text.startsWith("Bonjour")) event({ type: "error", code: "not_english", retryable: false });
    else event({ type: "result", result: { ...result, wordCount: text.trim().split(/\s+/).length } });
    res.end();
    return;
  }
  const json = (value) => {
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify(value));
  };
  switch (pathname) {
    case "/health": return json({ ok: true });
    case "/stored": return json(stored.get(searchParams.get("id")) ?? null);
    case "/siteverify": {
      const params = new URLSearchParams(raw);
      const token = req.headers["content-type"]?.includes("application/json") ? JSON.parse(raw).response : params.get("response");
      return json({ success: token === "browser-test-token", hostname: "127.0.0.1", action: "quick_check" });
    }
    case "/rest/v1/rpc/consume_quota":
    case "/rest/v1/rpc/use_retry": return json(true);
    case "/rest/v1/engine_status": return json([{ last_seen: new Date().toISOString() }]);
    case "/rest/v1/result_cache": {
      const hit = cache.get(searchParams.get("key")?.replace(/^eq\./, ""));
      return json(hit ? [hit] : []);
    }
    case "/rest/v1/rpc/store_check": {
      const check = JSON.parse(raw);
      stored.set(check.p_id, check);
      cache.set(check.p_key, {result: check.p_result, backend: check.p_backend});
      return json(null);
    }
    default: res.statusCode = 404; return json({});
  }
}).listen(4328, "127.0.0.1");
