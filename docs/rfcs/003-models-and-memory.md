# RFC 003 · Deep models and memory

Deep uses two causal language models with a shared tokenizer. The base model supplies the observer distribution and the instruct model supplies the performer distribution. The M6 keeps one pair resident alongside the fp32 Quick LM and encoder. Each active Deep essay has its own KV caches. The scheduler admits one Deep request and up to four Quick requests at a time.

## Candidate selection

Use Falcon-7B base/instruct for the published Binoculars comparison on the L40S. Qwen2.5-7B base/instruct is the 7B family evaluated on the M6. SmolLM2-135M base/instruct provides a small CPU integration fixture and a measured lower-memory comparison.

Fit each variant on the same source groups and reserve a separate validation cohort for choosing precision. A candidate needs a measured process peak at or below 18 GiB and a high-band ESL false-positive rate at or below 5%. Rank eligible variants by essay TPR at 1% FPR, then ESL false-positive rate, then peak memory. A complete selection also needs the bf16 comparison. When a precision exceeds the cap, record the measured or projected footprint and its basis. Keep the final test cohort separate from this choice.

## Runtime measurements

Metal's allocator limit and the service's admission check both use 18 GiB. The admission check reads the process's physical footprint, which includes memory charged to Metal. Load verification records the kernel's lifetime peak, signed request latency and the co-resident backup job's health. The latency gates are two seconds at p95 for five concurrent 1,000-word Quick submissions and 25 seconds for 2,000-word Deep submissions.

The [Phase 1 measurements](../plans/phase-1-evidence.md) identify the actual checkpoints, hardware results and experiment settings. A production release also requires the [calibration and parity gates](004-calibration-and-uncertainty.md).
