# Phase 1 · Deep checks and the sentence heatmap

1. Validate shared-tokenizer next-token reductions against the published E3 and E4 definitions. Compare cached and full-context scores, including the first token after each chunk boundary.
2. Reproduce the Falcon bf16 reference result on a pinned corpus. Compare quantized pairs with the same reference cohort, memory measurements and Metal/CUDA traces. Record missing measurements explicitly.
3. Split the source documents before building mixed essays. Fit E5, E7 and the caution classifiers on training partitions. Calibrate the Deep stacker separately and score the untouched test partition, including TOEFL coverage, sentence F1 and bootstrap uncertainty.
4. Generate the shared wire models. Stream UTF-16 offsets and numeric evidence for completed chunks. Test interrupted streams, retries, cache identity, per-mode quotas and text-free receipts.
5. Exercise the heatmap with pointer, keyboard, list view and reduced motion. Drive the methodology charts from measured report data and explain the 50% reference prior.
6. Measure a five-client Quick workload and 2,000-word Deep workload on the M6, recording p95, peak memory and beat-ad health. Preserve the held-out gates and report evidence separately for each backend.

Every result includes an interval, one-tap explanations and “A detector score is a reason to look closer, never proof.” Quick requires 150 English words and Deep requires 300. Keep text in the browser except during transient inference. Keep essay text out of logs and server-side storage. Use local models, free-tier resources and approved research data. Use strict ESM TypeScript, WCAG AA contrast, underline cues and reduced-motion fades of at most 150 ms.
