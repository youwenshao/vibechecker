# Paraphrase development audit

The ordinary validation stratum has two machine-origin academic abstracts from two publisher prompt groups. Both transformed records link to their clean machine parent, and both match the publisher's source and generator fields. Neither case resembles its same-prompt human original under either text comparison in this audit. The largest case-folded token sequence match against the human original is 0.0632. Neither shares a contiguous five-token sequence with the human original. Both pass the deployed English and word-count checks. These comparisons test publisher linkage and detectable copying. They cannot independently verify who authored a publisher's original.

| Frozen model | Anchored probability before isotonic | After length-specific isotonic | Displayed indices | Brier on the two abstracts |
| --- | ---: | ---: | ---: | ---: |
| v2 incumbent | .00140–.98015 | .00000–.99611 | 0, 100 | .5000 |
| Ordinary probe, anchor .50 | .00235–.99193 | .01126–.98923 | 1, 99 | .4901 |
| Ordinary probe, anchor .75 | .00189–.98666 | .00900–.99445 | 1, 99 | .4901 |
| Rewrite-origin probe, anchor .50 | .03420–.99616 | .00000–1.00000 | 0, 100 | .5000 |
| Rewrite-origin probe, anchor .75 | .04167–.99304 | .00000–1.00000 | 0, 100 | .5000 |

All five displayed mean probabilities equal .50 on this all-machine stratum, giving .50 ECE. The frozen stack and calibration data each include 13 machine-origin and one human-origin academic paraphrase. For the rewrite-origin candidate with anchor .75 the observed machine probabilities before isotonic range from .373 to 1.000 on the stack and from .793 to .999 on calibration. On the independent matched books/news stress sample, the same candidate puts 43 of 64 human-origin rewrites at the exact isotonic zero and 31 of 64 machine-origin rewrites at one. The JSON records endpoint counts, unique values, ranges, loss and fitted calibration knots by model, role, origin and domain. Each of the four CPU-replayed candidates reproduced its complete original validation and stress metrics before its diagnostics were accepted. [Development integrity measurements](rewrite-development-integrity.json)

The independent academic registration includes 66 machine-origin rewritten abstracts from six generators, 54 exact clean machine parents and 11 same-prompt clean machine substitutes. Its registration contains no release-length human originals. The private membership file includes hashed documents and groups and has a fixed source order. Reconstruction verifies the original group, rewrite-document and combined-document commitments. [Source registration](encoder-rewrite-validation.json) · [Reconstruction](academic-development-reconstruction.json)

## Independent academic development results

The production-profile extractor completed all 131 academic documents. The incumbent detected 66 of 66 rewritten groups at its high threshold. The two fixed rewrite-origin challengers also detected 66 of 66. Each ordinary-probe challenger detected 65 of 66. A two-sided 95% Wilson interval for 66 of 66 independent groups spans 94.5% to 100%. All five models detected the 54 exact clean parents. On the 11 clean substitutes, the incumbent and ordinary challengers detected all 11, and both rewrite-origin challengers detected 10. [Academic numeric evidence](academic-development-features.json) · [Frozen academic baseline measurements](academic-development-baselines.json)

| Frozen model | Rewrites above the high threshold | Anchored range before isotonic | Range after isotonic | Displayed Brier |
| --- | ---: | ---: | ---: | ---: |
| v2 incumbent | 66/66 | .739–1.000 | .768–1.000 | .00160 |
| Ordinary probe, anchor .50 | 65/66 | .267–1.000 | .270–1.000 | .00885 |
| Ordinary probe, anchor .75 | 65/66 | .497–1.000 | .350–1.000 | .00752 |
| Rewrite-origin probe, anchor .50 | 66/66 | .778–1.000 | .776–1.000 | .00121 |
| Rewrite-origin probe, anchor .75 | 66/66 | .672–1.000 | .605–1.000 | .00314 |

The independent academic source check recovered the same publisher parent ID, source group and generator for 66 of 66 rewrites. None matched the near-copy rule against the exact clean machine parent or same-prompt human original. All passed the application checks.

## Commands

Use the original Phase 1 checkout and pinned sources. These examples use the calibration artifact paths from the M6 run. The academic extraction uses the same `mlx-metal` checkpoints and `VIBECHECKER_QUICK_PREFILL=512` as the v1 parent. Numeric extraction is resumable. The standalone model comparison runs on CPU and emits aggregate statistics.

```sh
python -m vibechecker_eval.academic_development \
  --prior-report eval/reports/phase-1/encoder-rewrite-validation.json \
  --cache ../eval/.cache --base-features calibration-v2/stack.sqlite \
  --plan-out calibration-v3/academic-development-plan.json \
  --summary-out calibration-v3/academic-development-reconstruction.json

python -m vibechecker_eval.academic_features \
  --prior-report eval/reports/phase-1/encoder-rewrite-validation.json \
  --plan calibration-v3/academic-development-plan.json \
  --cache ../eval/.cache --base-features calibration-v2/stack.sqlite \
  --selection calibration-v3/selection.json --parent deep-qwen7b-q4-p512-v1.joblib \
  --sidecar calibration-v3/academic-development.sqlite \
  --out calibration-v3/academic-development-features.json

python -m vibechecker_eval.rewrite_diagnostics \
  --parent deep-qwen7b-q4-p512-v1.joblib --incumbent deep-qwen7b-q4-p512-v2.joblib \
  --probe calibration-v3/rewrite-probe-v1/origin-probe-v1.joblib \
  --features calibration-v2/stack.sqlite --sidecar calibration-v3/rewrite-stack.sqlite \
  --supplement calibration-v2/rewrite-origin-v1/verified-cohort.sqlite \
  --original-selection calibration-v2/selection.json --selection calibration-v3/selection.json \
  --cache ../eval/.cache --out calibration-v3/plateau-audit.json \
  --academic-plan calibration-v3/academic-development-plan.json \
  --academic-features calibration-v3/academic-development.sqlite \
  --academic-binding calibration-v3/academic-development-features.json \
  --control-keys calibration-v3/human-controls.sqlite \
  --encoder-fit-keys calibration-v2/encoder.sqlite \
  --encoder-fit-keys calibration-v2/expanded-probe-v1/encoder-expanded.sqlite \
  --academic-out calibration-v3/academic-development-baselines.json
```
