# Phase 1.1 blocker report

**Deep v4 remains ineligible.** Every frozen policy exceeds the 0.08 worst-group calibration limit on both final cohorts. The guarded cutoff gave the lowest observed human-essay error, but still flagged 4/115 historical essays and 4/36 Liang admissions essays. Its 5/267 combined estimate reuses all 36 historical admissions essays. The independent reservation contains zero new admissions sources. [Frozen protocol](protocol.md) · [Fitted cutoffs and calibration membership](policy.json) · [Complete group scorecards, intervals and gate checks](metrics.json)

## Held-out decisions

Each entry counts high-band decisions at the inclusive cutoff. The original test contains 221 documents. The prospective audit scored 435 of 512 reserved documents. The coverage sensitivity analysis contains 471 documents, including 267 human essays.

| Measure | v4, cutoff 24 | Empirical subgroup cutoff | Guarded subgroup cutoff |
|---|---:|---:|---:|
| Historical human essays | 6/115 (5.22%) | 8/115 (6.96%) | 4/115 (3.48%) |
| Liang human admissions essays | 6/36 (16.67%) | 8/36 (22.22%) | 4/36 (11.11%) |
| Prospective human essays, Liang absent | 3/231 (1.30%) | 4/231 (1.73%) | 1/231 (0.43%) |
| Combined human essays, historical Liang included | 9/267 (3.37%) | 12/267 (4.49%) | 5/267 (1.87%) |
| Historical generated documents detected | 69/69 | 69/69 | 69/69 |
| Prospective generated documents detected | 177/178 | 177/178 | 175/178 |
| Maximum historical metric regression against v2, limit 0.01 | 0.1220 | 0.1389 | 0.1220 |

The guarded policy's 95% Wilson interval is **4.41–25.31%** on Liang and **0.80–4.31%** on the combined essays. Both additional machine misses were among the nine Cohere Chat documents in the prospective audit. The guarded policy detected 7/9, down from 9/9. The largest guarded regression against v2 was the mixed-or-higher rate on 600–1,199-word humans. The empirical policy's largest regression was the high-band rate on Liang.

The score-adjustment candidate chose exponent **1** in both supported calibration cells. Its decisions and probabilities exactly reproduce the empirical policy. High-band cutoffs alone cannot alter ten-bin ECE. Historical pooled ECE was **0.0229**, with **0.1800** on four paraphrases. Prospective pooled ECE was **0.0087**, with **0.1250** on eight Cohere documents. In the combined analysis, the 23 Liang admissions essays of 600–1,199 words had ECE **0.1378**, the largest error after adding source-by-length groups.

## Source and length results

Human and machine columns give high-band counts in v4 / empirical / guarded order. The score-adjusted policy matched the empirical policy in every cell. The machine-readable scorecards also give Wilson intervals and the generator, attack, writer and genre breakdowns.

### Original test

| Source | Words | Human N | Human high | Machine N | Machine high | ECE |
|---|---|---:|---:|---:|---:|---:|
| asap | 300-599 | 24 | 0 / 0 / 0 | 0 | — | 0.0000 |
| asap | 600-1199 | 2 | 0 / 0 / 0 | 0 | — | 0.0000 |
| ellipse | 300-599 | 23 | 0 / 0 / 0 | 0 | — | 0.0000 |
| ellipse | 600-1199 | 6 | 0 / 0 / 0 | 0 | — | 0.0000 |
| liang/college | 300-599 | 13 | 2 / 2 / 2 | 5 | 5 / 5 / 5 | 0.0633 |
| liang/college | 600-1199 | 23 | 4 / 6 / 2 | 0 | — | 0.1378 |
| liang/hewlett | 300-599 | 23 | 0 / 0 / 0 | 0 | — | 0.0000 |
| liang/hewlett | 600-1199 | 1 | 0 / 0 / 0 | 0 | — | 0.0000 |
| raid-attacks | 300-599 | 1 | 1 / 1 / 1 | 24 | 24 / 24 / 24 | 0.0308 |
| raid | 1200+ | 1 | 0 / 0 / 0 | 0 | — | 0.0000 |
| raid | 300-599 | 26 | 1 / 1 / 0 | 40 | 40 / 40 / 40 | 0.0132 |
| raid | 600-1199 | 9 | 0 / 0 / 0 | 0 | — | 0.0133 |

### Independent audit

| Source | Words | Human N | Human high | Machine N | Machine high | ECE |
|---|---|---:|---:|---:|---:|---:|
| asap | 1200+ | 1 | 0 / 0 / 0 | 0 | — | 0.0000 |
| asap | 300-599 | 58 | 1 / 1 / 0 | 0 | — | 0.0119 |
| asap | 600-1199 | 56 | 0 / 0 / 0 | 0 | — | 0.0014 |
| ellipse | 1200+ | 1 | 0 / 0 / 0 | 0 | — | 0.0000 |
| ellipse | 300-599 | 73 | 1 / 2 / 1 | 0 | — | 0.0105 |
| ellipse | 600-1199 | 42 | 1 / 1 / 0 | 0 | — | 0.0150 |
| raid-attacks | 300-599 | 0 | — | 86 | 86 / 86 / 86 | 0.0078 |
| raid | 1200+ | 8 | 0 / 0 / 0 | 0 | — | 0.0000 |
| raid | 300-599 | 9 | 0 / 0 / 0 | 92 | 91 / 91 / 89 | 0.0143 |
| raid | 600-1199 | 9 | 0 / 0 / 0 | 0 | — | 0.0000 |

## How the policies were fitted

The M6 scored numeric feature rows through the frozen v4 readout after reproducing the historical alias quarantine. The fit used 1,346 ordinary calibration documents, including 914 humans. No Liang record entered this fit. The guarded rule used cutoff 24 in the pooled and 300–599-word cells, and 80 for 600–1,199 words. Source-by-length overrides included 58 for short eligible ASAP essays and 85 for short eligible RAID passages. Every eligible cell, threshold and fallback is in the policy receipt. On 268 development documents the guarded rule flagged 2/138 human essays and detected 77/80 machine texts. The empirical cutoffs flagged 8/138 and detected 78/80. Worst development ECE was 0.4800 for both. The frozen policy SHA-256 is `307b8dee047d15668858b8150146ffa6d84d2fc203627da81984de38bee0a0e9`. [Development scorecards](validation.json) · [Fit receipt](policy.json)

## Admissions coverage

All 70 pinned human admissions essays were accounted for. Thirty were assigned to the development fold. Of the 40 historical-final-fold essays, 36 were scored and four were refused by the existing English-language check. The prospective source pool contains no eligible independent Liang admissions component. Matching on length, or resampling the 36 scores, cannot supply an unseen source.

The coverage sensitivity analysis adds the 36 historical humans to the 435 prospective documents exactly once. The join verified normalized document IDs and source IDs. The original prospective reservation had already excluded historical source components, including linked duplicates. A fresh independent human-FP gate remains unresolved for this cohort. [Reservation and isolation checks](../prospective-audit-reservation.json)

The prospective and combined samples contain zero generated essay-domain documents, leaving essay AUROC unmeasured in both. They also lack the native-proxy comparator for the ESL gap. The original test has five generated essays and a measured essay AUROC of 1.0000. Both final samples lack a release-length TOEFL/native comparison.

## Short TOEFL essays

The pinned release has **91 records, 90 distinct normalized texts**, ranging from 62 to 148 words. Product Deep refused all 91 as too short. The M6 research run processed the original text of every record through the v4 pair, encoder probe, stacker and length fallback. At cutoff 24 the false-positive rate was **24/91 (26.37%, 95% Wilson 18.41–36.25%)**. The duplicate was below cutoff. The distinct-text estimate was **24/90 (26.67%)**. The guarded policy also flagged 24/91. The empirical and score-adjusted policies used the pooled fallback of 21 and flagged **32/91 (35.16%)**. The release-length TOEFL gate still has zero eligible observations.

## Workstation hardware

The tailnet workstation ran Ubuntu 24.04.4 LTS on a Ryzen 9 9950X3D with one GeForce RTX 5090 (32,607 MiB, driver 595.99.02). The locked environment used MLX 0.32.4, mlx-lm 0.32.2, Torch 2.15.0 and Transformers 5.23.0. Both local runs used the same v4 digest, checkpoint and tokenizer hashes, prefill, held-out IDs and UTF-16 offsets as the M6 report.

The full CUDA replay took **137.22 s**. All **221 indexes** and **5,236 sentence spans** matched the archived M6 Metal trace. One sentence exceeded the 0.02 limit. Its score was 0.253382 on Metal and 0.228442 on CUDA, a difference of **0.024940**. The affected span covered UTF-16 offsets 360–3,044 in a 374-word RAID-attacks MPT Chat passage in the perplexity-misspelling stratum. The workstation comparison fails the sentence gate. The first CUDA attempt exhausted memory in the Quick LM. Limiting the MLX scratch cache to 512 MiB and total MLX memory to 23 GiB left room for the Torch encoder during the successful replay.

The workstation CPU replay took **23,872.36 s (6 h 37 min 52 s)**. Its 221 document indexes and 5,236 sentence spans matched CUDA exactly. Two sentence scores in two documents exceeded 0.02. The largest difference was **0.043854** on the same RAID-attacks passage, with a CPU score of 0.272296. The other span, at UTF-16 offsets 0–17, scored 0.422627 on CPU and 0.447979 on CUDA, a difference of **0.025352**. Both local comparisons fail sentence parity. [Hardware, trace hashes and backup events](hardware.json)

Native packed MLX CPU did not finish a four-token base-model preflight in 10 min 31 s. For the full CPU reference, MLX expanded the pinned pair's affine Q4 projection weights in their checkpoint dtype, and Torch performed the dense CPU matrix multiplies. The research runner identifies this path as `mlx-cpu-dense-q4`. Both replays used the same tokenizer, frozen readouts and stacker. Native packed CPU coverage for the full Deep cohort remains unmeasured.

The repository's Quick LM parity command also compared 127 next-token predictions on the public Thoreau fixture. CUDA versus native MLX CPU maximum absolute differences were 0.025280 in log probability, 12 rank positions and 0.021815 in entropy. Against Torch CPU fp32 they were 0.025122, 13 and 0.021211 respectively.

Only the workstation container `beat-ad-beta-backup-1` was paused. The following times are Shanghai time on 21 November 2026. Docker reported running and unpaused before and after each window.

| Workload | Paused | Restored | Elapsed |
|---|---:|---:|---:|
| Initial CUDA replay, memory exhaustion | 15:34:41 | 15:35:53 | 72 s |
| Complete 221-document CUDA replay | 15:36:19 | 15:38:40 | 141 s |
| Quick token comparison | 15:39:13 | 15:39:21 | 8 s |

The CPU-only reference ran with CUDA hidden. The backup was running and unpaused at 22:14 Shanghai time after the CPU trace completed. Both temporary research copies of the raw fixture cache were removed after digest verification. A subsequent duplicate CPU invocation encountered the retired cache before scoring and left the verified trace intact. The original plan still requires the Falcon L40S bf16 reference and hosted measurements. Modal remains on hold.

## Reproduction

The M6 passed all 103 baseline Python tests in 5.39 s. With the five added cases, the final run passed all 108 in 5.18 s using `PYTHONPATH=engine/src:eval/src:services/inference/src ~/vibechecker/venv/bin/python -m pytest -q`. On Windows with Node 24.19.0 and pnpm 10.30.2, `pnpm verify` passed the contract checks, TypeScript and all 13 unit tests in 9.88 s wall time. The production-build Playwright run passed all 13 tests in 17.0 s with `pnpm --filter @vibechecker/web e2e`.

Run from the repository root with the pinned Python environment. On the M6, `$research` is the existing `~/vibechecker/phase1-check` directory, `$cache` is `~/vibechecker/eval/.cache`, and `$output` is a separate research output directory. Set the four checkpoint paths, the v4 joblib, Metal backend and Quick prefill 512 as in the Phase 1 evidence. The v4 artifact SHA-256 is `aeafbb70201caec3029b24799faedd8fee89aacf5ef1bdf09e1eee2673b82d9b`. Fitting took 2.06 s wall time, the TOEFL measurement took 60.48 s including model load, and the final cohort replay took 11.56 s.

```sh
export PYTHONPATH=engine/src:eval/src:services/inference/src
version=deep-qwen7b-q4-p512-v4
python -m vibechecker_eval.phase11 fit \
  --model "$research/$version.joblib" --parent "$research/deep-qwen7b-q4-p512-v1.joblib" \
  --features "$research/calibration-v2/stack.sqlite" --cache "$cache" \
  --out "$output/policy.json" --validation "$output/validation.json"
python -m vibechecker_eval.short_toefl --cache "$cache" \
  --model-sha256 aeafbb70201caec3029b24799faedd8fee89aacf5ef1bdf09e1eee2673b82d9b \
  --out "$output/toefl.json"
python -m vibechecker_eval.phase11 evaluate --policy "$output/policy.json" \
  --policy-sha256 307b8dee047d15668858b8150146ffa6d84d2fc203627da81984de38bee0a0e9 \
  --original "$research/$version.test.metal.json" \
  --audit "$research/calibration-v4-academic/$version.prospective.metal.json" \
  --cache "$cache" --short "$output/toefl.json" --out "$output/metrics.json"
```

On the M6, export only the committed historical documents to a private research corpus cache. Transfer that cache, the reference trace, the frozen joblib and the four checkpoint directories over the tailnet. Set the same checkpoint paths and prefill on the workstation. The evaluator verifies weight bytes, the artifact digest, cohort membership and prefill before comparison.

```sh
umask 077
python -m vibechecker_eval.workstation_parity --reference "$research/$version.test.metal.json" \
  --export-from-cache "$cache" --fixtures "$output/historical.jsonl.gz"

# Workstation, from its research checkout. Both environments use uv.lock.
UV_PROJECT_ENVIRONMENT=../env uv sync --frozen --package vibechecker-engine --extra cuda --package vibechecker-eval
UV_PROJECT_ENVIRONMENT=../env-cpu uv sync --frozen --package vibechecker-engine --extra cpu --package vibechecker-eval
export PYTHONPATH=engine/src:eval/src VIBECHECKER_QUICK_PREFILL=512 HF_HUB_OFFLINE=1
export OMP_NUM_THREADS=12 MKL_NUM_THREADS=12 OPENBLAS_NUM_THREADS=1
VIBECHECKER_BACKEND=mlx-cuda ../env/bin/python -m vibechecker_eval.workstation_parity \
  --reference ../reference.json --fixtures ../corpus-cache/historical.jsonl.gz --trace-out ../rtx.json
CUDA_VISIBLE_DEVICES="" VIBECHECKER_BACKEND=mlx-cpu \
  LD_PRELOAD="$PWD/../env-cpu/lib/python3.12/site-packages/torch/lib/libtorch_cpu.so" \
  ../env-cpu/bin/python -m vibechecker_eval.workstation_parity --dense-cpu \
  --reference ../reference.json --fixtures ../corpus-cache/historical.jsonl.gz --trace-out ../cpu.json
LD_PRELOAD="$PWD/../env/lib/python3.12/site-packages/torch/lib/libtorch_cpu.so" \
  ../env/bin/python engine/tools/check_parity.py "$VIBECHECKER_LM" ../thoreau-1000.txt \
  --tokens 128 --backend mlx-cuda
```

Each GPU command ran inside a shell that verified the container was running and unpaused, captured its Docker ID, registered an exit trap, then ran `docker pause "$unit"`. The trap ran `docker unpause "$unit"` and inspected the restored state. The CPU-only command ran outside this wrapper. For the Deep trace comparison, call `vibechecker_eval.deep_cohort.parity(cuda, cpu, local_cpu_cuda=True)` on the two decoded JSON files. The default comparator accepts Metal and CUDA traces for the hardware gate.
