import { createServer } from "node:http";
import { createHash, randomUUID } from "node:crypto";

const engineVersion = "e2e-quick";
const stored = new Map();
const cache = new Map();
const heldHeatmaps = new Map();
const codes = new Map(), inbox = new Map(), users = new Map(), tokens = new Map();
const usage = new Map();
const base64 = value => Buffer.from(JSON.stringify(value)).toString("base64url");
const result = {
  index: 62, interval: { low: 48, high: 75 }, band: "mixed", wordCount: 180,
  lenses:{version:1,turnitin:null,gptzero:"mixed",zerogpt:"high",grammarly:"mixed",veriguide:"low"},
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
      event({ type: "result", result: { ...result, lenses:{...result.lenses,turnitin:"masked"}, wordCount: words, flags: text.startsWith("Full kit") ? ["esl","laundering","invisible","homoglyph"] : ["esl"], sentences,
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
  const input = raw && req.headers["content-type"]?.includes("json") ? JSON.parse(raw) : {};
  const user = users.get(tokens.get(req.headers.authorization?.slice(7)));
  if(pathname.startsWith("/auth/v1/admin/users/")) {
    const id=pathname.split("/").at(-1);
    if(req.method==="GET") return json(users.get(id));
    for(const [key,row] of stored) if(row.p_owner===id) stored.delete(key);
    const old=users.get(id); users.delete(id); return json(old);
  }
  switch (pathname) {
    case "/inbox": return json(inbox.get(searchParams.get("email")) ?? null);
    case "/auth/v1/otp": {
      if(!input.gotrue_meta_security?.captcha_token || !input.code_challenge) {res.statusCode=400;return json({});}
      const code=randomUUID();
      codes.set(code,input.code_challenge);
      const link=new URL(searchParams.get("redirect_to"));link.searchParams.set("code",code);
      inbox.set(input.email,link.href);return json({});
    }
    case "/auth/v1/token": {
      if(!codes.has(input.auth_code) || createHash("sha256").update(input.code_verifier).digest("base64url")!==codes.get(input.auth_code)) {
        res.statusCode=400;return json({});
      }
      codes.delete(input.auth_code);
      const id=randomUUID(), exp=Math.floor(Date.now()/1000)+3600;
      const access=base64({alg:"HS256",typ:"JWT"})+"."+base64({sub:id,exp,role:"authenticated"})+".dGVzdA";
      const member={id,aud:"authenticated",role:"authenticated",app_metadata:{},user_metadata:{},created_at:new Date().toISOString()};
      users.set(id,member);tokens.set(access,id);
      return json({access_token:access,refresh_token:randomUUID(),token_type:"bearer",expires_in:3600,expires_at:exp,user:member});
    }
    case "/auth/v1/authorize": {
      if(searchParams.get("provider")!=="google" || !searchParams.get("code_challenge")) {res.statusCode=400;return json({});}
      const code=randomUUID(), callback=new URL(searchParams.get("redirect_to"));
      codes.set(code,searchParams.get("code_challenge"));callback.searchParams.set("code",code);
      res.writeHead(302,{location:callback.href});return res.end();
    }
    case "/auth/v1/user":
      if(!user){res.statusCode=401;return json({message:"No session"});}return json(user);
    case "/auth/v1/logout": return json({});
    case "/rest/v1/rpc/claim_check": {
      const row=stored.get(input.p_id);
      if(!row || row.p_owner || row.p_claim_hash!==input.p_hash)return json(false);
      row.p_owner=input.p_owner;row.p_claim_hash=null;return json(true);
    }
    case "/rest/v1/checks": {
      const owner=searchParams.get("user_id")?.slice(3), id=searchParams.get("id")?.slice(3);
      const rows=[...stored.values()].filter(row=>row.p_owner===owner && (!id || row.p_id===id));
      if(req.method==="DELETE") {
        if(!user || user.id!==owner){res.statusCode=403;return json({});}
        for(const row of rows)stored.delete(row.p_id);return json(null);
      }
      return json(rows.reverse().map(row=>({id:row.p_id,mode:row.p_mode,engine_version:row.p_version,
        word_count:row.p_result.wordCount,result:row.p_result,expires_at:new Date(Date.now()+30*86400000).toISOString()})));
    }
    case "/rest/v1/rpc/read_saved_essay": {
      const row=stored.get(input.p_id);return json(row?.p_owner===input.p_owner ? row.p_envelope : null);
    }
    case "/continue-heatmap": heldHeatmaps.get(searchParams.get("fixture") ?? "stream")?.(); return json(true);
    case "/health": return json({ ok: true });
    case "/stored": return json(stored.get(searchParams.get("id")) ?? null);
    case "/siteverify": {
      const params = new URLSearchParams(raw);
      const token = req.headers["content-type"]?.includes("application/json") ? JSON.parse(raw).response : params.get("response");
      return json({ success: ["browser-test-token", "browser-deep-token","auth-test-token"].includes(token), hostname: "127.0.0.1", action: token==="auth-test-token" ? "auth_check" : token === "browser-deep-token" ? "deep_check" : "quick_check" });
    }
    case "/rest/v1/rpc/device_usage": return json(usage.get(input.p_device)??{quick:0,deep:0});
    case "/rest/v1/rpc/check_quota": {
      const counts=usage.get(input.p_device)??{quick:0,deep:0};
      counts[input.p_mode]++;usage.set(input.p_device,counts);return json(true);
    }
    case "/rest/v1/rpc/use_retry": return json(true);
    case "/rest/v1/engine_status": return json([{ last_seen: new Date().toISOString() }]);
    case "/rest/v1/result_cache": {
      const hit = cache.get(searchParams.get("key")?.replace(/^eq\./, ""));
      return json(hit ? [hit] : []);
    }
    case "/rest/v1/rpc/store_account_check": {
      const check = JSON.parse(raw);
      stored.set(check.p_id, check);
      cache.set(check.p_key, {result: check.p_result, backend: check.p_backend});
      return json(null);
    }
    default: res.statusCode = 404; return json({});
  }
}).listen(4328, "127.0.0.1");
