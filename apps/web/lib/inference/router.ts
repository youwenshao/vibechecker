import { InferenceEvent, type Mode, type SentenceScore } from "@vibechecker/contracts";
import { env, signedHeaders } from "../server/security";

interface Routing {
  mode?: Mode;
  lastSeen?: string;
  forceFallback: boolean;
  signal: AbortSignal;
  fetcher?: typeof fetch;
  headerTimeout?: number;
}
export class UpstreamUnavailable extends Error {}

export async function routeInference(text: string, options: Routing) {
  const body = JSON.stringify({ text, mode: options.mode ?? "quick" });
  const send = async (primary: boolean) => {
    const base = env(primary ? "PRIMARY_INFERENCE_URL" : "FALLBACK_INFERENCE_URL");
    const headers: Record<string, string> = {
      "content-type": "application/json",
      ...signedHeaders("POST", "/v1/analyze", body),
    };
    if (primary && process.env.CF_ACCESS_CLIENT_ID) {
      headers["CF-Access-Client-Id"] = process.env.CF_ACCESS_CLIENT_ID;
      headers["CF-Access-Client-Secret"] = env("CF_ACCESS_CLIENT_SECRET");
    }
    const timer = new AbortController();
    // Clear the header deadline once connected. An active stream has a separate total deadline.
    const timeout = setTimeout(
      () => timer.abort(),
      primary ? (options.headerTimeout ?? 3000) : 90000,
    );
    try {
      const response = await (options.fetcher ?? fetch)(new URL("/v1/analyze", base), {
        method: "POST",
        headers,
        body,
        redirect: "error",
        cache: "no-store",
        signal: AbortSignal.any([options.signal, timer.signal, AbortSignal.timeout(120000)]),
      });
      if (
        response.ok &&
        response.body &&
        response.headers.get("content-type")?.includes("application/x-ndjson")
      )
        return { response, primary };
      await response.body?.cancel();
      if (response.status >= 500) throw new UpstreamUnavailable();
      throw Error("Unexpected inference response");
    } finally {
      clearTimeout(timeout);
    }
  };
  const age = Date.now() - Date.parse(options.lastSeen ?? "");
  if (!options.forceFallback && age >= -60000 && age <= 180000) {
    try {
      return await send(true);
    } catch (error) {
      if (
        options.signal.aborted ||
        !(
          error instanceof UpstreamUnavailable ||
          error instanceof TypeError ||
          (error instanceof Error && ["AbortError", "TimeoutError"].includes(error.name))
        )
      )
        throw error;
    }
  }
  return await send(false);
}

const quickSignals = ["e1", "e2", "e6", "stylometry"] as const;
const deepSignals = [...quickSignals, "e3", "e4", "e5", "e7"] as const;

// UTF-16 indices are end-exclusive and must not split a surrogate pair.
export function validSentences(text: string, items: SentenceScore[], previousEnd = 0) {
  function boundary(offset: number) {
    const before = text.charCodeAt(offset - 1);
    const after = text.charCodeAt(offset);
    return !(before >= 0xd800 && before <= 0xdbff && after >= 0xdc00 && after <= 0xdfff);
  }
  for (const item of items) {
    if (item.start < previousEnd || item.start >= item.end || item.end > text.length ||
        !boundary(item.start) || !boundary(item.end)) return false;
    previousEnd = item.end;
  }
  return true;
}

export function validScore(score: Extract<InferenceEvent, { type: "result" }>["result"], mode: Mode, text: string) {
  const expected = mode === "deep" ? deepSignals : quickSignals;
  const ids = new Set(score.signals.map((signal) => signal.id));
  return score.interval.low <= score.index && score.index <= score.interval.high &&
    score.signals.length === expected.length && expected.every((id) => ids.has(id)) &&
    (mode === "deep" ? score.wordCount >= 300 && score.wordCount <= 2500 && Boolean(score.sentences?.length) &&
      validSentences(text, score.sentences!) : !score.sentences?.length);
}

export async function* events(stream: ReadableStream<Uint8Array>) {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let tail = "";
  const parse = (line: string) => {
    if (line.length > 1024 * 1024) throw Error("Oversized event");
    const event = InferenceEvent.parse(JSON.parse(line));
    return event;
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      tail += decoder.decode(value, { stream: true });
      let end;
      while ((end = tail.indexOf("\n")) >= 0) {
        if (end) yield parse(tail.slice(0, end));
        tail = tail.slice(end + 1);
      }
      if (tail.length > 1024 * 1024) throw Error("Oversized event");
    }
    tail += decoder.decode();
    if (tail.trim()) yield parse(tail);
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
