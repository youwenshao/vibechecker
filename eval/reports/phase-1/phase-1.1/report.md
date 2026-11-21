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

## How the policies were fitted

The M6 scored numeric feature rows through the frozen v4 readout after reproducing the historical alias quarantine. The fit used 1,346 ordinary calibration documents, including 914 humans. No Liang record entered this fit. The guarded rule used cutoff 24 in the pooled and 300–599-word cells, and 80 for 600–1,199 words. Source-by-length overrides included 58 for short eligible ASAP essays and 85 for short eligible RAID passages. Every eligible cell, threshold and fallback is in the policy receipt. On 268 development documents the guarded rule flagged 2/138 human essays and detected 77/80 machine texts. The empirical cutoffs flagged 8/138 and detected 78/80. Worst development ECE was 0.4800 for both. The frozen policy SHA-256 is `307b8dee047d15668858b8150146ffa6d84d2fc203627da81984de38bee0a0e9`. [Development scorecards](validation.json) · [Fit receipt](policy.json)

## Admissions coverage

All 70 pinned human admissions essays were accounted for. Thirty were assigned to the development fold. Of the 40 historical-final-fold essays, 36 were scored and four were refused by the existing English-language check. The prospective source pool contains no eligible independent Liang admissions component. Matching on length, or resampling the 36 scores, cannot supply an unseen source.

The coverage sensitivity analysis adds the 36 historical humans to the 435 prospective documents exactly once. The join verified normalized document IDs and source IDs. The original prospective reservation had already excluded historical source components, including linked duplicates. A fresh independent human-FP gate remains unresolved for this cohort. [Reservation and isolation checks](../prospective-audit-reservation.json)

## Short TOEFL essays

The pinned release has **91 records, 90 distinct normalized texts**, ranging from 62 to 148 words. Product Deep refused all 91 as too short. The M6 research run processed the original text of every record through the v4 pair, encoder probe, stacker and length fallback. At cutoff 24 the false-positive rate was **24/91 (26.37%, 95% Wilson 18.41–36.25%)**. The duplicate was below cutoff. The distinct-text estimate was **24/90 (26.67%)**. The guarded policy also flagged 24/91. The empirical and score-adjusted policies used the pooled fallback of 21 and flagged **32/91 (35.16%)**. The release-length TOEFL gate still has zero eligible observations.

## Reproduction

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
