# Phase 0 verification

## M6 inference

On 20 November 2026 the `youwenshao` account on the 32 GiB M6 ran the fp32 Quick engine through the `io.vibechecker.inference` user LaunchAgent. The signed health response through Cloudflare identified `mlx-metal` and engine version `quick-m6-fp32-v0`. Anonymous requests to the same endpoint received HTTP 403.

The probe sent the public 1,000-word Thoreau fixture through the Cloudflare Access policy, tunnel, HMAC check, scheduler and model. Twelve sequential requests from the Windows workstation measured p50 **1,007 ms** and p95 **1,772 ms**. The first response contained four signals, index 0 and interval 0–10. This measurement covers the inference endpoint. The latency target for a student also includes the browser, Turnstile, Vercel and Supabase.

```sh
node --env-file=apps/web/.env.local ops/probe-inference.mjs artifacts/thoreau-1000.txt 20
```

After a fresh install from commit `275d4a5`, the first signed analysis took **4,495 ms**. A subsequent 20-request run measured p50 **964 ms** and p95 **1,498 ms** through Cloudflare. The M6's local warm benchmark recorded p95 **625 ms** over 20 checks. The fixture recipe and SHA-256 digests identify the data and weights used. [Engine benchmark](../../engine/benchmarks/m6-phase0.json)

## Staging database and browser

Both migrations were applied to the Singapore Supabase Free staging project. Hosted SQL checks verified role privileges, the device and address caps, single-use retry tokens, monotonic heartbeats, 30-day record expiry and rollback isolation. The browser suite exercised the production Next.js build, including cached re-checks with separate claim tokens, text-free persistence, interrupted-stream retry, file import, local deletion, axe and reduced motion. All eight browser tests passed with local upstream fixtures.

## Evaluation

The committed scorecards cover archived HFOpenAI predictions, a measured RoBERTa comparator and Quick on 436 held-out documents. The largest stratum calibration error exceeds the release gate and the TOEFL corpus cannot establish a Quick false-positive rate at the 150-word minimum. [Quick report](../../eval/reports/quick-m6-fp32-v0/report.md) · [RoBERTa report](../../eval/reports/roberta-large-liang-v1/report.md) · [Dataset review](../../eval/LICENSES.md)

A private R2 upload and independent restore matched all eight stored hashes, including the fitted stacker. [Restore manifest](../../eval/reports/r2-restore-2026-11-20.json)
