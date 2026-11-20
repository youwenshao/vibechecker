import { CheckResult, InferenceEvent } from "@vibechecker/contracts";
import { z } from "zod";

export type Verdict = z.infer<typeof CheckResult>;
export type Receipt = { result: Verdict; checkId: string; claimToken: string };
type Stage = "loading" | "scoring" | "fallback";
const completed = z.object({ result: CheckResult, checkId: z.uuid(), claimToken: z.string().min(1) });

export class CheckError extends Error {
  constructor(readonly code: string, readonly retryToken?: string) {
    super(code);
  }
}

async function readAttempt(
  text: string, turnstileToken: string, onStage: (stage: Stage) => void, retryToken?: string,
): Promise<Receipt> {
  const response = await fetch("/api/checks", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
    body: JSON.stringify({ text, mode: "quick", turnstileToken, retryToken }),
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
    if (event.type === "accepted") onStage(event.backend === "mlx-cuda" ? "fallback" : "loading");
    if (event.type === "progress") onStage("scoring");
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
      if (done || buffer.length > 256 * 1024) throw new CheckError("internal");
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function checkEssay(text: string, token: string, onStage: (stage: Stage) => void) {
  try {
    return await readAttempt(text, token, onStage);
  } catch (error) {
    if (!(error instanceof CheckError) || !error.retryToken) throw error;
    onStage("fallback");
    return readAttempt(text, token, onStage, error.retryToken);
  }
}
