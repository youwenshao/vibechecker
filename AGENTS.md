# VibeChecker

Work from the repository root with Node 24, pnpm 10.30.2 and Python 3.12 via uv. Read the Phase 0 plan in docs/plans before changing the Quick path.

- packages/contracts owns the wire format. Run `pnpm contracts:generate` after editing its Zod schemas and commit the JSON and Pydantic outputs.
- engine owns scoring. Keep model and artifact versions identical on Metal and CUDA. eval imports engine for training and reports.
- services/inference owns admission, signatures and NDJSON. The Next.js app talks only to this service and Supabase. Every success, refusal and error path must keep essay contents out of server-side persistence and logs.
- Run `pnpm verify`, `uv run pytest` and `pnpm --filter @vibechecker/web e2e`. Run the engine tests with the relevant hardware extra to exercise numerical parity.
- Display the interval, score explanation, detector limitations and the exact caution on every result. The held-out report determines release eligibility.
