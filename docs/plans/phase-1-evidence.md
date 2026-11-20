# Phase 1 verification

## Pair selection

The 4-bit and 6-bit Qwen2.5-7B pairs scored the same 54 validation documents. Both reached an essay TPR of 60% at the 1% FPR operating point. Neither placed any of the nine ESL essays in the high band (95% Wilson interval 0–29.9%). The prespecified memory tie-break advanced the 4-bit pair to testing. The validation process peaked at 12.91 GiB with 4 bits and 16.51 GiB with 6 bits. Mixed-sentence F1 was 0.731 and 0.755 respectively. The missing bf16 comparison keeps production selection open. [Bake-off](../../eval/reports/phase-1/bakeoff.json) · [4-bit validation](../../eval/reports/qwen-4bit-v1/report.md) · [6-bit validation](../../eval/reports/qwen-6bit-v1/report.md)

Each fit used 32 eligible source documents and four mixed documents for the sentence head, 43 independent documents for the stacker and 74 for calibration. Only nine human documents had usable writer-background labels for fitting the ESL caution classifier. The models are research artifacts.

## Streaming through a browser

A local production Next.js build sent the Phase 0 public 1,000-word Thoreau fixture to a signed, loopback-only service on the 32 GiB M6. The service shared the Quick extractor with a fitted SmolLM2-135M base/instruct pair. Chromium rendered seven sentence highlights at 261 ms, all 41 at 466 ms, and the eight-signal verdict at 1,093 ms. All UTF-16 offsets matched. The keyboard tooltip, arrow-key navigation and list view worked. This was one warm run with local Turnstile, quota, cache and receipt fixtures. [Browser observations](../../engine/benchmarks/m6-phase1-browser.json)

With the 4-bit Qwen2.5-7B pair, the same browser rendered its first seven highlights at 1.26 s, all 41 at 5.77 s and the verdict at 6.26 s. It showed an index of 48 with an interval of 7–73. All offsets, keyboard controls and list items passed. [Qwen browser observations](../../engine/benchmarks/m6-phase1-browser-qwen.json)

## Load and co-tenancy

The benchmark uses signed HTTP on M6 loopback, following one unmeasured warm-up per mode. Each round submits five distinct 1,000-word Quick requests together and one 2,000-word Deep request. It records the Darwin process's lifetime peak physical footprint, including compressed and GPU memory. It also reads the loaded status and last exit code of the co-resident `system/hk.beatad.px-backup` LaunchDaemon.

The final 4-bit service, `deep-qwen7b-q4-p512-v1`, completed all 120 requests. Quick p95 was **1.967 s** at five-way concurrency. Deep p95 was **12.146 s**, with first sentence chunks at **1.043 s** p95. Its lifetime peak was **15.45 GiB**. The backup job remained loaded with last exit code 0 in all 21 samples and completed two runs during the test. The service used 512-token prefill and the optimized Unicode preparation path. [Full load record](../../engine/benchmarks/m6-phase1-qwen-4bit-prefill512.json)

The smaller-pair run completed all 20 Deep requests at p95 1,831 ms. Of 100 concurrent-workload Quick requests, 99 completed at p95 3,064 ms and one received HTTP 503. Peak physical footprint was 5.16 GiB. The backup job stayed loaded with last exit code 0 throughout. [SmolLM2 load report](../../engine/benchmarks/m6-phase1-smol.json)

Raising Quick's prefill from 64 to 256 tokens and batching full encoder windows reduced single-request Quick p95 from 631 to 404 ms on the public fixture. All nine document features and the displayed verdict matched on that input. The 4-bit Qwen service with this profile completed all 100 Quick and 20 Deep requests. Quick p95 was 2.204 s, Deep p95 was 12.438 s and peak physical footprint was 13.99 GiB. The backup daemon recorded two additional runs with last exit code 0. [Prefill comparison](../../engine/benchmarks/m6-phase1-prefill.json) · [Qwen load report](../../engine/benchmarks/m6-phase1-qwen-4bit.json)

With a 512-token prefill, single-request Quick p95 was 371 ms across five warm runs on the same fixture. The largest absolute feature change was 0.00152 and the displayed index, interval and band matched the baseline. [512-token comparison](../../engine/benchmarks/m6-phase1-prefill-512.json)

## Held-out data

The 4-bit Qwen runtime scored **221** eligible test documents (152 human, 69 generated) after screening 266 candidates. Pooled AUROC was **0.9325**. Essay AUROC was 1.0000 on 115 human essays and only five generated essays. No human essay reached the high band (95% Wilson interval 0–3.2%); the corresponding interval for zero high scores among 32 ESL essays was 0–10.7%. All 91 pinned TOEFL essays fell below 300 words, leaving that comparison unmeasured. [Held-out scorecard](../../eval/reports/phase-1/report.md)

Across 1,132 sentences in held-out mixed documents, precision was 0.840, recall was 0.506 and F1 was **0.632**. Pooled expected calibration error was **0.0801** against a limit of 0.05. The largest stratum error was **0.8300** against a limit of 0.08, in the four-document Cohere generator stratum. These failures keep the release gate closed. The evaluation metadata links the fitted artifact to the same successful M6 load workload by digest and runtime profile. [Machine-readable results](../../eval/reports/phase-1/report.json)

The SmolLM2 comparison used 221 held-out documents. Its pooled calibration error was 0.0296 and its worst-stratum error was 0.5200, above the 0.08 limit. Sentence F1 was 0.6241 across 1,132 held-out mixed-document sentences. Only five generated essays qualified in its 120-essay discrimination cohort. The 91 pinned TOEFL essays all fell below the Deep length minimum. The false-positive estimate for that cohort is unavailable. [SmolLM2 scorecard](../../eval/reports/smol-calibrated-v1/report.md)

The operator retained the hosted Modal hold. The Falcon L40S bf16 reproduction, hosted training and Metal/CUDA parity therefore have no live results. Local CPU and Metal tests cover the official-function numerical goldens, cached chunk boundaries, the native Falcon implementation and quantized checkpoint reloads.

## Software verification

The Python suite passed all 53 tests on the M6. Linux CPU passed 52 with the Metal-only case skipped. The pinned SmolLM2 pair produced identical E3 and E4 values on Linux with a fresh download and an offline cache. The generated contracts matched their schemas, TypeScript compiled and all 13 web unit tests passed. All 13 Playwright tests passed against the production build and the measured scorecard, including keyboard access, axe checks, retry after interrupted streaming and verification of the calibration chart's values. Both SQL test files passed on a disposable Supabase PostgreSQL 17 instance.

## Reproducing the Qwen runs

The 4-bit weights came from `mlx-community/Qwen2.5-7B-4bit` at `fd815ff0a73b38d0fb29c00a57cca80fe778462c` and `mlx-community/Qwen2.5-7B-Instruct-4bit` at `c26a38f6a37d0a51b4e9a1eb3026530fa35d9fed`. The 6-bit pair used `engine/tools/quantize_pair_member.py --bits 6` on `Qwen/Qwen2.5-7B` at `d149729398750b98c0af14eb82c78cfe92750796` and `Qwen/Qwen2.5-7B-Instruct` at `a09a35458c702b33eeacc393d103063234e8bc28`. Each scored report records the checkpoint and fitted-model digests.

Set the two Quick checkpoint paths and the pair paths as described in the [engine setup](../../engine/README.md). Both validation fits used the following parameters, a fresh output file per precision and 64 tokens per Quick prefill.

```sh
uv run vibechecker-eval deep --datasets raid raid-attacks asap ellipse liang \
  --cohort validation --pair-family Qwen2.5-7B --limit-per-class 16 --seed 42 \
  --version "$version" --model-out "$version.joblib" --trace-out "$version.validation.metal.json"
```

The M6 memory preflight projected 20.01 GiB for the 8-bit pair. It added the increase in published packed weight bytes for both models to the measured 4-bit peak, assuming comparable non-weight allocations. This exceeded the 18 GiB budget before scoring. [Calculation and pinned revisions](../../eval/reports/phase-1/8bit-memory-preflight.json)

For the independent test, reuse the fitted 4-bit joblib. This run used seed 42 and raised the per-class, per-dataset, per-split reservoir limit to 72. On the verification host, the fitted file and test trace are under `~/vibechecker/phase1-check/`. Local copies are in `eval/artifacts/phase-1/`.

```sh
VIBECHECKER_QUICK_PREFILL=512 uv run vibechecker-eval deep \
  --datasets raid raid-attacks asap ellipse liang --cohort test --pair-family Qwen2.5-7B \
  --limit-per-class 72 --seed 42 --version deep-qwen7b-q4-p512-v1 \
  --model-in eval/artifacts/phase-1/deep-qwen7b-q4-p512-v1.joblib \
  --trace-out eval/artifacts/phase-1/deep-qwen7b-q4-p512-v1.test.metal.json \
  --bakeoff-report eval/reports/phase-1/bakeoff.json \
  --load-report engine/benchmarks/m6-phase1-qwen-4bit-prefill512.json
```
