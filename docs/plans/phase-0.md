# Phase 0 · Quick checks

Start with the evaluation harness, then connect the same Quick engine to both inference hosts and the paste UI.

1. Verify dataset provenance, pin checksums and test the loader against corrupted or disallowed inputs. Produce a baseline report with explicit missing strata and hardware evidence.
2. Exercise Unicode offsets, refusal boundaries, cached token statistics and the PyTorch reference before fitting E1, E2, E6 and stylometry. Separate training, calibration and evaluation. Report the 50% prior, bootstrap uncertainty and gates.
3. Define the score and stream in Zod. Generate Python validation from the exported schema. Test signatures, replay, scheduler backpressure, memory pressure, heartbeat and a complete inference stream.
4. Verify primary, busy, stale, timeout and interrupted streams. Verify atomic quotas and that only validated numerical results and opaque identifiers reach storage.
5. Exercise the paste and file paths, results, explanations, claim-token storage and forgetting through the web UI. Check keyboard access, contrast, axe and reduced motion.
6. Run the same version and artifacts on M6 Metal and Modal CUDA. Record the M6 timing and parity separately from CPU or mock runs. Exercise staging failover before calling the demo ready.

Every result includes its interval, one-tap explanations and “A detector score is a reason to look closer, never proof.” Quick accepts English essays of 150–5,000 words. Deep starts at 300 words in Phase 1. The UI supports reduced motion with transitions at most 150 ms and accessible non-colour cues. Only the browser keeps essay text. The web proxy and model receive it transiently. No third-party detector API, essay logging or plaintext persistence. Keep the deployment on the plan's free tiers and the research data within its permitted uses. Use strict ESM TypeScript and document reasons for non-obvious choices.
