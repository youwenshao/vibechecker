import { createServer } from "node:http";

const engineVersion = "e2e-quick";
const stored = new Map();
const cache = new Map();
const heldHeatmaps = new Map();
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
    const { text, mode } = JSON.parse(raw);
    const event = (value) => res.write(JSON.stringify(value) + "\n");
    res.writeHead(200, { "Content-Type": "application/x-ndjson" });
    const primary = Boolean(req.headers["cf-access-client-id"]);
    const promised = text.startsWith("Missing chunk") ? 3 : 2;
    event({ type: "accepted", engineVersion, chunks: mode === "deep" ? promised : 1, backend: primary ? "mlx-metal" : "mlx-cuda" });
    if (text.startsWith("Failover") && primary) return res.end();
    if (mode === "deep") {
      const words = text.trim().split(/\s+/).length;
      if (words < 300) {
        event({ type: "error", code: "too_short", retryable: false });
        return res.end();
      }
      const sentences = [...text.matchAll(/[^.!?]+[.!?]/g)].map((match, i) => ({
        start: match.index + match[0].length - match[0].trimStart().length,
        end: match.index + match[0].length, score: i % 2 ? .82 : .28, signals: i % 2 ? ["e4", "e5"] : ["e3"],
      }));
      event({ type: "progress", stage: "deep", done: 0, total: 2 });
      event({ type: "sentences", items: sentences.slice(0, 1) });
      if (text.startsWith("Interrupted") && primary) return res.end();
      if (text.startsWith("Stream demo") || text.startsWith("Interrupted browser")) {
        await new Promise((resolve) => {
          const timeout = setTimeout(resolve, 20000);
          heldHeatmaps.set(text.startsWith("Interrupted") ? "interrupted" : "stream", () => { clearTimeout(timeout); resolve(); });
        });
      }
      event({ type: "sentences", items: sentences.slice(1) });
      event({ type: "progress", stage: "deep", done: 2, total: 2 });
      event({ type: "result", result: { ...result, wordCount: words, flags: ["esl"], sentences,
        signals: [...result.signals, ...["e3", "e4", "e5", "e7"].map((id) => ({id, value: .42, humanReference: .5}))],
      } });
      return res.end();
    }
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
    case "/continue-heatmap": heldHeatmaps.get(searchParams.get("fixture") ?? "stream")?.(); return json(true);
    case "/health": return json({ ok: true });
    case "/stored": return json(stored.get(searchParams.get("id")) ?? null);
    case "/siteverify": {
      const params = new URLSearchParams(raw);
      const token = req.headers["content-type"]?.includes("application/json") ? JSON.parse(raw).response : params.get("response");
      return json({ success: ["browser-test-token", "browser-deep-token"].includes(token), hostname: "127.0.0.1", action: token === "browser-deep-token" ? "deep_check" : "quick_check" });
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
