# VibeChecker · Phase 0

Quick checks score English essays of 150–5,000 words. Each result includes four signal comparisons, a calibrated index, a bootstrap interval and two explanations. **A detector score is a reason to look closer, never proof.**

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

The browser suite builds and starts the real Next.js app with local test doubles for remote services. For a connected development run, configure the variables in `apps/web/.env.example`, apply both Supabase migrations, then run `pnpm --filter @vibechecker/web dev`. The public widget key must be set at build time. The API signs a device cookie, verifies Turnstile, atomically charges daily quotas, checks the versioned cache and proxies NDJSON. Only a completed score reaches the database. The browser stores the essay and claim token locally for up to 30 days, with immediate erasure on request.

## Inference and evaluation

The primary is a loopback FastAPI process on port 8317 on the M6. The dedicated `io.vibechecker.inference` and `io.vibechecker.cloudflared` LaunchAgents run in the existing `youwenshao` login. Their files and models live under `~/vibechecker`. On a restart the login session must be available for its LaunchAgents. The tunnel forwards only the protected inference hostname. The Access token and body HMAC are independent checks.

The mode, tokenizer, weights, calibration artifact and engine version must agree between the primary and Modal. Choose a new engine version when any score-producing input changes. Set the secret `ENGINE_VERSION` and `INFERENCE_HMAC_SECRET` on both hosts. The M6 also needs `HEARTBEAT_URL=https://staging.vibechecker.io/api/engine/heartbeat` in its private `service.json`.

```sh
ops/m6/deploy.sh <git-ref> <engine-version>
uv run --package vibechecker-modal modal deploy modal/fallback.py
node --env-file=apps/web/.env.local ops/probe-inference.mjs
```

Use the Modal volume `vibechecker-weights` for both pinned checkpoints and `quick.joblib`. The Modal secret is `vibechecker-inference`. The release workflow re-scores the held-out corpus on CUDA and compares it with the same model's Metal trace in `/weights/traces/<engine-version>.metal.json`. Its exit status includes the quality and parity gates. The benchmark record identifies the exact fixture, model revisions and fitted artifact.

- [Model setup and feature definitions](engine/README.md)
- [Registry, baseline, Quick fit and R2 transfer commands](eval/README.md)
- [Measured M6 latency and numerical parity](engine/benchmarks/m6-phase0.json)
- [Held-out Quick report and release gates](eval/reports/quick-m6-fp32-v0/report.md)
- [Calibration decision](docs/rfcs/004-calibration-and-uncertainty.md)
