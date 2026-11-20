import { z } from "zod";

export const Backend = z.enum(["mlx-metal", "mlx-cuda", "mlx-cpu"]);
export const AnalyzeRequest = z.strictObject({
  text: z.string().min(1).max(200_000),
  mode: z.literal("quick"),
});

const Index = z.int().min(0).max(100);
export const CheckResult = z.strictObject({
  index: Index,
  interval: z.strictObject({ low: Index, high: Index }),
  band: z.enum(["low", "mixed", "high"]),
  wordCount: z.int().min(150).max(5000),
  signals: z
    .array(
      z.strictObject({
        id: z.enum(["e1", "e2", "e6", "stylometry"]),
        value: z.number(),
        humanReference: z.number(),
        samples: z.array(z.number()).min(2).max(16).optional(),
      }),
    )
    .length(4),
  flags: z.array(z.enum(["invisible", "homoglyph"])).max(2),
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
    stage: z.enum(["quick", "scoring"]),
    done: z.int().nonnegative(),
    total: z.int().positive(),
  }),
  z.strictObject({
    type: z.literal("sentences"),
    items: z.array(
      z.strictObject({
        start: z.int().nonnegative(),
        end: z.int().positive(),
        score: z.number().min(0).max(1),
      }),
    ),
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
