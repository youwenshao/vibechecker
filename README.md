# VibeChecker

Quick checks score English essays of 150–5,000 words using four signals. Deep checks accept 300–2,500 English words, stream a sentence heatmap and return eight signal comparisons. Both modes show a calibrated index, a bootstrap interval and two explanations. **A detector score is a reason to look closer, never proof.**

## Run and verify

Use Node 24, pnpm 10.30.2 and Python 3.12. On Linux or macOS, run the following from the repository root.

```sh
pnpm install --frozen-lockfile
uv sync --locked --all-packages
pnpm verify
uv run pytest
pnpm --filter @vibechecker/web exec playwright install chromium
pnpm --filter @vibechecker/web e2e
```

The browser suite builds and starts the real Next.js app with local test doubles for remote services. For a connected development run, configure the variables in `apps/web/.env.example`, apply the Supabase migrations in order, then run `pnpm --filter @vibechecker/web dev`. The public widget key must be set at build time. The API signs a device cookie, verifies Turnstile, atomically charges daily quotas, checks the versioned cache and proxies NDJSON. Deep cache keys include the exact submitted string so cached sentence offsets remain valid. Only a completed score reaches the database. The browser stores the essay and claim token locally for up to 30 days, with immediate erasure on request.

## Inference and evaluation

The primary is a loopback FastAPI process on port 8317 on the M6. The dedicated `io.vibechecker.inference` and `io.vibechecker.cloudflared` LaunchAgents run in the existing `youwenshao` login. Their files and models live under `~/vibechecker`. On a restart the login session must be available for its LaunchAgents. The tunnel forwards only the protected inference hostname. The Access token and body HMAC are independent checks.

The mode, tokenizer, weights, calibration artifact and engine version must agree between the primary and Modal. Choose a new engine version when any score-producing input changes. Set the secret `ENGINE_VERSION` and `INFERENCE_HMAC_SECRET` on both hosts. The M6 also needs `HEARTBEAT_URL=https://staging.vibechecker.io/api/engine/heartbeat` in its private `service.json`.

```sh
ops/m6/deploy.sh <git-ref> <engine-version>
uv run --package vibechecker-modal modal deploy modal/fallback.py
node --env-file=apps/web/.env.local ops/probe-inference.mjs
node --env-file=apps/web/.env.local ops/probe-inference.mjs --target fallback
```

Use the Modal volume `vibechecker-weights` for both pinned checkpoints and `quick.joblib`. The Modal secret is `vibechecker-inference`. The release workflow re-scores the held-out corpus on CUDA and compares it with the same model's Metal trace in `/weights/traces/<engine-version>.metal.json`. Its exit status includes the quality and parity gates. The benchmark record identifies the exact fixture, model revisions and fitted artifact.

- [Model setup and feature definitions](engine/README.md)
- [Registry, baseline, Quick fit and R2 transfer commands](eval/README.md)
- [Measured M6 latency and numerical parity](engine/benchmarks/m6-phase0.json)
- [Held-out Quick report and release gates](eval/reports/quick-m6-fp32-v0/report.md)
- [Deep model selection and memory limits](docs/rfcs/003-models-and-memory.md)
- [Calibration decision](docs/rfcs/004-calibration-and-uncertainty.md)

## Run Deep on the M6

Set `VIBECHECKER_PAIR_OBSERVER` to the local base checkpoint, `VIBECHECKER_PAIR_PERFORMER` to the matching instruct checkpoint, and `VIBECHECKER_DEEP_MODEL` to the trusted fitted Deep artifact. The native service reads absolute paths from its existing private `service.json`. For Modal the volume defaults are `/weights/pair/base`, `/weights/pair/instruct` and `/weights/deep.joblib`. Set the same new `ENGINE_VERSION` on the service and web router. Quick-only installations can retain their Phase 0 configuration.

The service checks the Deep artifact's checkpoint hashes on startup. The browser renders each chunk using UTF-16 offsets into the submitted essay. The methodology pages at `/en/methodology` and `/zh-HK/methodology` read aggregate evaluation reports at build time.

Run the signed load test on the M6 with the port and PID of the service under test. It records time to first Deep chunk, nearest-rank p95, the kernel's lifetime peak physical footprint and the co-resident beat-ad backup job's status. A failed gate returns a nonzero exit code and retains the measurements.

```sh
python ops/m6/phase1_load.py /path/to/public-essay.txt --config ~/vibechecker/service.json \
  --pid <inference-pid> --out m6-load.json
```

[Phase 1 evidence](docs/plans/phase-1-evidence.md) · [Deep training and evaluation](eval/README.md#deep-evaluation)
