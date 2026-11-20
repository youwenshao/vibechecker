// Run with node --env-file=apps/web/.env.local ops/probe-inference.mjs [public-essay.txt] [runs].
import {readFileSync} from "node:fs";
import {createHash, createHmac, randomUUID} from "node:crypto";
const [input, runs = "1"] = process.argv.slice(2);
const path = input ? "/v1/analyze" : "/v1/health";
const method = input ? "POST" : "GET";
const body = input ? JSON.stringify({mode:"quick",text:readFileSync(input,"utf8")}) : "";
const url = new URL(path,process.env.PRIMARY_INFERENCE_URL);
const access = {
  "CF-Access-Client-Id": process.env.CF_ACCESS_CLIENT_ID,
  "CF-Access-Client-Secret": process.env.CF_ACCESS_CLIENT_SECRET,
};
const count = Number(runs);
if (!Number.isInteger(count) || count < 1 || count > 100) throw Error("Choose 1 to 100 probes");
const latencies = [];
for (let i = 0; i < count; i++) {
  const stamp = String(Math.floor(Date.now()/1000));
  const nonce = randomUUID();
  const hash = createHash("sha256").update(body).digest("hex");
  const mac = createHmac("sha256",process.env.INFERENCE_HMAC_SECRET)
    .update([method,path,stamp,nonce,hash].join("\n")).digest("hex");
  const start = performance.now();
  const r = await fetch(url,{method,body:input ? body : undefined,redirect:"manual",
    headers:{...access,"content-type":"application/json","x-vibe-time":stamp,"x-vibe-id":nonce,"x-vibe-signature":mac},
    signal:AbortSignal.timeout(90000)});
  if (!r.ok) throw Error("Inference HTTP "+r.status);
  if (!input) {
    console.log(await r.json());
    break;
  }
  const events = (await r.text()).trim().split("\n").map(JSON.parse);
  const last = events.at(-1);
  if (last?.type !== "result") throw Error("Inference ended with "+last?.code);
  latencies.push(Math.round(performance.now()-start));
  if (i === 0) console.log({backend:events[0].backend,version:events[0].engineVersion,
    words:last.result.wordCount,index:last.result.index,interval:last.result.interval,signals:last.result.signals.length});
}
if (latencies.length) {
  latencies.sort((a,b)=>a-b);
  console.log({runs:count,p50_ms:latencies[Math.ceil(0.5*count)-1],p95_ms:latencies[Math.ceil(0.95*count)-1]});
}
