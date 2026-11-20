import type { Backend, CheckResult } from "@vibechecker/contracts";
import { env } from "./security";

async function rest(path: string, payload?: unknown) {
  const key = env("SUPABASE_SERVICE_ROLE_KEY");
  const response = await fetch(new URL("/rest/v1/" + path, env("SUPABASE_URL")), {
    method: payload === undefined ? "GET" : "POST",
    headers: {
      apikey: key,
      ...(key.startsWith("sb_secret_") ? {} : { authorization: "Bearer " + key }),
      "content-type": "application/json",
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(6000),
  });
  if (!response.ok) throw Error("Storage unavailable");
  const raw = await response.text();
  return raw ? JSON.parse(raw) : null;
}

export async function consumeQuota(device: string, address: string): Promise<boolean> {
  return (await rest("rpc/consume_quota", { p_device: device, p_address: address })) === true;
}
export async function spendRetry(hash: string): Promise<boolean> {
  return (await rest("rpc/use_retry", { p_nonce: hash })) === true;
}
export async function cached(key: string) {
  const rows = await rest(
    `result_cache?select=result,backend&key=eq.${key}&expires_at=gt.${encodeURIComponent(new Date().toISOString())}&limit=1`,
  );
  return rows[0];
}
export async function primaryHeartbeat(version: string): Promise<string | undefined> {
  const rows = await rest(
    `engine_status?select=last_seen&id=eq.primary&engine_version=eq.${encodeURIComponent(version)}&limit=1`,
  );
  return rows[0]?.last_seen;
}
export async function heartbeat(version: string, time: number) {
  // Store the signed time; redelivering a pulse can never extend its lifetime.
  await rest("rpc/record_heartbeat", {
    p_version: version,
    p_time: new Date(time * 1000).toISOString(),
  });
}
export interface Completed {
  id: string;
  key: string;
  claimHash: string;
  version: string;
  backend: Backend;
  result: CheckResult;
}
export async function storeCheck(entry: Completed) {
  const payload = {
    p_id: entry.id,
    p_key: entry.key,
    p_claim_hash: entry.claimHash,
    p_version: entry.version,
    p_backend: entry.backend,
    p_result: entry.result,
  };
  // The check ID makes a retry safe after an ambiguous network timeout.
  try {
    await rest("rpc/store_check", payload);
  } catch {
    await rest("rpc/store_check", payload);
  }
}
