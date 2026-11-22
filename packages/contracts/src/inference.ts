import { z } from "zod";

export const Backend = z.enum(["mlx-metal", "mlx-cuda", "mlx-cpu"]);
export const Mode = z.enum(["quick", "deep"]);
export type Mode = z.infer<typeof Mode>;
export const AnalyzeRequest = z.strictObject({
  text: z.string().min(1).max(200_000),
  mode: Mode,
});

export const SignalId = z.enum(["e1", "e2", "e3", "e4", "e5", "e6", "e7", "stylometry"]);
export type SignalId = z.infer<typeof SignalId>;
export const SentenceScore = z.strictObject({
  start: z.int().nonnegative(),
  end: z.int().positive(),
  score: z.number().min(0).max(1),
  signals: z.array(SignalId).max(8),
});
export type SentenceScore = z.infer<typeof SentenceScore>;
const Index = z.int().min(0).max(100);
const LensBand = z.enum(["low", "mixed", "high"]);
export const Lenses = z.strictObject({
  version: z.literal(1),
  turnitin: z.union([z.literal("masked"), z.literal(0), z.int().min(20).max(100)]).nullable(),
  gptzero: LensBand,
  zerogpt: LensBand,
  grammarly: LensBand,
  veriguide: LensBand,
});
const Signal = z.strictObject({
  id: SignalId,
  value: z.number(),
  humanReference: z.number(),
  samples: z.array(z.number()).min(2).max(16).optional(),
});
export const CheckResult = z.strictObject({
  lenses: Lenses.optional(),
  index: Index,
  interval: z.strictObject({ low: Index, high: Index }),
  band: z.enum(["low", "mixed", "high"]),
  wordCount: z.int().min(150).max(5000),
  signals: z.union([z.array(Signal).length(4), z.array(Signal).length(8)]),
  flags: z.array(z.enum(["invisible", "homoglyph", "esl", "laundering"])).max(4),
  sentences: z.array(SentenceScore).min(1).optional(),
});
export type CheckResult = z.infer<typeof CheckResult>;
export const Version = z.string().regex(/^[a-zA-Z0-9._-]{1,64}$/);
export const InferenceEvent = z.discriminatedUnion("type", [
  z.strictObject({
    type: z.literal("accepted"),
    backend: Backend,
    engineVersion: Version,
    chunks: z.int().positive(),
  }),
  z.strictObject({
    type: z.literal("progress"),
    stage: z.enum(["quick", "deep", "scoring"]),
    done: z.int().nonnegative(),
    total: z.int().positive(),
  }),
  z.strictObject({
    type: z.literal("sentences"),
    items: z.array(SentenceScore).min(1),
  }),
  z.strictObject({ type: z.literal("result"), result: CheckResult }),
  z.strictObject({
    type: z.literal("error"),
    code: z.enum(["too_short", "too_long", "not_english", "busy", "internal"]),
    retryable: z.boolean(),
  }),
]);
export type InferenceEvent = z.infer<typeof InferenceEvent>;
export type Backend = z.infer<typeof Backend>;
