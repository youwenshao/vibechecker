import { CheckResult, InferenceEvent, type Mode, type SentenceScore } from "@vibechecker/contracts";
import { z } from "zod";

export type Verdict = z.infer<typeof CheckResult>;
export type Receipt = { result: Verdict; checkId: string; claimToken: string; engineVersion?:string; owner?:string|null };
export type Stage = "loading" | "scoring" | "fallback";
interface StreamObserver {
  stage: (stage: Stage) => void;
  sentences: (items: SentenceScore[]) => void;
  reset: () => void;
}
const completed = z.object({ result: CheckResult, checkId: z.uuid(), claimToken: z.string().min(1), engineVersion:z.string().optional(), owner:z.uuid().nullish() });

export class CheckError extends Error {
  constructor(readonly code: string, readonly retryToken?: string) {
    super(code);
  }
}

async function readAttempt(
  text: string, mode: Mode, turnstileToken: string, observer: StreamObserver, saveText: boolean, retryToken?: string,
): Promise<Receipt> {
  const response = await fetch("/api/checks", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
    body: JSON.stringify({ text, mode, turnstileToken, saveText, retryToken }),
  });
  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => null);
    throw new CheckError(typeof error?.code === "string" ? error.code : "internal");
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  const handleLine = (line: string) => {
    const data = JSON.parse(line);
    if (data.type === "result") return completed.parse(data);
    const { retryToken: permit, ...wire } = data;
    const event = InferenceEvent.parse(wire);
    if (event.type === "error") throw new CheckError(event.code,
      event.retryable && typeof permit === "string" ? permit : undefined);
    if (event.type === "accepted") observer.stage(event.backend === "mlx-cuda" ? "fallback" : "loading");
    if (event.type === "progress") observer.stage("scoring");
    if (event.type === "sentences") observer.sentences(event.items);
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer += value ?? "";
      const lines = buffer.split("\n");
      buffer = lines.pop()!;
      if (done && buffer.trim()) lines.push(buffer);
      for (const line of lines) {
        if (line.trim()) {
          const receipt = handleLine(line);
          if (receipt) return receipt;
        }
      }
      if (done || buffer.length > 1024 * 1024) throw new CheckError("internal");
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function checkEssay(text: string, mode: Mode, token: string, observer: StreamObserver, saveText = false) {
  try {
    return await readAttempt(text, mode, token, observer, saveText);
  } catch (error) {
    if (!(error instanceof CheckError) || !error.retryToken) throw error;
    observer.reset();
    observer.stage("fallback");
    return readAttempt(text, mode, token, observer, saveText, error.retryToken);
  }
}
