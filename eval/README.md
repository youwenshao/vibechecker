# Evaluation

Run from the repository root with the Python 3.12 uv workspace. The registry is the SHA-256 manifest. Every enabled loader verifies local and downloaded files against it. The same commands run on the M6 and in the Modal eval job.

```sh
uv run vibechecker-eval baseline
uv run hf download openai-community/roberta-large-openai-detector \
  --revision 38f3e0ccf205e9c4e0b38ae9d75ec948141bf832 \
  --include '*.json' '*.txt' model.safetensors --local-dir eval/.cache/roberta-large
uv run vibechecker-eval baseline --roberta-dir eval/.cache/roberta-large --version roberta-large-liang-v1
uv run vibechecker-eval fetch --datasets raid liang ellipse
uv run vibechecker-eval quick --datasets raid liang ellipse --limit-per-class 96 --seed 42 \
  --version quick-m6-fp32-v0 --model-out eval/artifacts/quick.joblib --trace-out eval/artifacts/metal.json
```

The first command replays archival scores distributed with Liang et al.'s research corpus. The independent RoBERTa comparator verifies a pinned checkpoint and measures it on the same essays, including the short TOEFL submissions. It uses the first 510 content tokens and the original class ordering. Its PyTorch and Transformers dependencies are shared with the engine's inference extra. [Reference implementation](https://github.com/openai/gpt-2-output-dataset/blob/master/detector/server.py) · [Model card](https://huggingface.co/openai-community/roberta-large-openai-detector)

A Quick run loads the engine's pinned LM and encoder through `VIBECHECKER_LM`, `VIBECHECKER_ENCODER` and `VIBECHECKER_BACKEND`. For a Modal job, place its cache, reports and optional trace under the mounted volume, for example `--cache /weights/datasets --reports /weights/reports --trace-out /weights/traces/cuda.json`. All scoring runs locally on the named backend.

Use `--model-in` to score the same selection with an existing fitted model. On a CUDA host, add `--compare-trace eval/artifacts/metal.json` to measure paired index deltas. Use `--previous path/to/report.json` to test regressions on an identical held-out cohort. `--enforce` exits nonzero when quality or document parity gates have missing evidence or fail. Quick produces document scores. Sentence F1 and sentence parity apply when the sentence head arrives in Phase 1.

Selection is deterministic with a fixed dataset order and seed. RAID variants sharing the publisher's source ID stay in one partition. Human essay corpora split on the normalized text hash. Cross-source exact duplicates are removed. The per-class reservoir cap applies separately to each dataset, label and partition. Zero uses every eligible document. The loader retains upstream language-background labels where available. Unknown writer status stays unknown. Reuse of RAID/MAGE by the frozen encoder means their results are in-domain measurements.

Reports include AUROC, empirical TPR at attainable FPR of at most 1%, ten-bin ECE, Brier score and Wilson intervals for human false positives at both band thresholds. Calibration uses the engine's balanced reference prior. Test-set ECE and Brier use the observed class proportions. Latency covers feature extraction and prediction on the named backend. End-to-end HTTP latency requires a separate run. A missing class yields an undefined discrimination metric.

Private R2 sync uses the standard AWS credential chain, `R2_ENDPOINT_URL` and the bucket argument. Each object is named by its digest. Downloads verify the bytes before atomically replacing the cache entry.

On 20 November 2026, the private `vibechecker-artifacts` bucket passed a live restore through Cloudflare's REST API. All six report files, the fitted Quick stacker and a 64-row PADBen ID/label projection matched their source digests after downloading into a separate local directory. [Restore manifest](reports/r2-restore-2026-11-20.json)

The clean RAID artifact is 801,662,741 bytes. It exceeds the REST upload limit of 300 MB. Bulk sync uses boto3's S3 multipart uploads. Configure `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` for Object Read & Write scoped to `vibechecker-artifacts`, together with its R2 endpoint. Temporary credentials also require `AWS_SESSION_TOKEN`. The M6 and development host lacked these bucket credentials during verification, so the full RAID transfer is pending. [R2 authentication](https://developers.cloudflare.com/r2/api/tokens/) · [REST upload limits](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/objects/methods/upload/)

```sh
uv run vibechecker-eval sync push --bucket vibechecker-artifacts --datasets raid liang
uv run vibechecker-eval sync pull --bucket vibechecker-artifacts --datasets raid liang
```

Training accepts `--commercial-only` and fails explicitly if the resulting training or calibration partition lacks either label. Sources and project usage decisions are recorded in [the verification report](LICENSES.md).

## Deep evaluation

The paired rewrite study covers human- and machine-origin paraphrases from two English domains. Its source audit, licensing and reproduction command are documented in the [Phase 1 rewrite supplement](reports/phase-1/rewrite-origin-supplement.md).

The [paraphrase development audit](reports/phase-1/paraphrase-development.md) traces frozen model probabilities through calibration and checks the publisher parents of academic rewrites. It includes commands to reconstruct the separate 66-source academic development cohort and its original clean controls.

Fit from pinned local checkpoints. `VIBECHECKER_LM` and `VIBECHECKER_ENCODER` point to the Quick models. `VIBECHECKER_PAIR_OBSERVER` points to the base model and `VIBECHECKER_PAIR_PERFORMER` to its instruct counterpart. Sampling, training and validation run locally on the named MLX backend. Use the same file contents on both inference hosts.

```sh
uv run vibechecker-eval deep --version phase-1 --seed 42 --limit-per-class 96 \
  --datasets raid raid-attacks asap ellipse liang --model-out eval/artifacts/deep.joblib \
  --trace-out eval/artifacts/phase-1.metal.json
```

The fit partitions related RAID prompt variants together and removes duplicate texts across sources. A second group split separates training the heads from training the document stacker. The mixed-document builder splices contiguous excerpts within each partition and derives its sentence labels using the production splitter. ELL heads use publisher-labeled human examples. Unknown backgrounds contribute no ELL training labels. The laundering classifier learns the distinction between the clean and attacked RAID samples. Its evaluation measures this proxy task. The calibration partition fits balanced-prior isotonic curves and band thresholds. `--commercial-only` applies the registry restrictions to both fitting and evaluation.

Test and bake-off validation use different source groups. The scorecard reports mixed-document sentence F1, the document metrics, observed reliability bins, refusal counts, calibration thresholds and confidence intervals for the false-positive rates. Short TOEFL essays count toward refusals. A zero denominator leaves their false-positive rate unmeasured.

The fitted artifact records its training seed, per-class reservoir limit and dataset order under `fit_selection`. A later `--model-in` evaluation can use a larger independent reservoir or a different seed. Its report preserves the original fit settings and records the current evaluation settings under `scope`. Earlier artifacts without this metadata show a null fit selection.

Deep uses the Quick language model for several document features. Its effective token count per prefill appears as `quick_prefill` in both the report and parity trace. Set `VIBECHECKER_QUICK_PREFILL` to reproduce that profile. New fits also record their original prefill under `fit_selection`. Metal and CUDA parity requires the same evaluation prefill. Earlier traces used 64 tokens.

The M6 load gate matches the artifact, version and prefill against the scoring trace. It recomputes nearest-rank p95 from 20 complete 2,000-word Deep streams and 100 complete 1,000-word Quick checks at concurrency five. It also requires a healthy beat-ad job sample before the workload and after each of the 20 rounds.

**Falcon reference reproduction.** Figure 11 reports an AUROC of 0.9933 on the CNN articles paired with LLaMA-2-13B continuations. The job fetches the pinned Falcon base and instruct revisions and verifies the original bf16 shard digests. It uses the first 512 tokens, unmodified text, and the negative Binoculars ratio. The default run selects 64 paired records with seed 42. Set `--pairs 0` for all 2,207 pairs. The subset check uses an absolute tolerance of 0.01 against the published AUROC and reports a paired bootstrap interval. The report records the corpus, selection digest, GPU and measured score. A smaller subset is a plumbing check. [Published paper](https://proceedings.mlr.press/v235/hans24a.html) · [Authors’ experiment](https://github.com/ahans30/Binoculars/blob/c8ae2f90d50ee696418bc71d8d9e5020e5f9d7b8/experiments/jobs.sh)

```sh
uv run --package vibechecker-modal python -m modal run modal/phase1.py::reproduce --pairs 64
```

**Quantization selection.** For each model family, score the bf16 reference on an L40S. Account for each of 4, 6 and 8 bits with a scored Metal run or a documented preflight above 18 GiB. Use the same `deep --cohort validation` fit with a distinct `--version` and artifact output for each scored precision. Keep `--pair-family`, seed, dataset order and sample limits fixed. The selector ranks scored candidates that fit within 18 GiB and meet the 5% ESL false-positive gate. It uses essay TPR at 1% FPR, then ESL false-positive rate, then memory usage. The JSON lists differences from bf16 for each scored candidate.

```sh
uv run vibechecker-eval bakeoff eval/reports/{qwen-bf16,qwen-4,qwen-6,qwen-8}/report.json \
  --out eval/artifacts/bakeoff.json
uv run --package vibechecker-modal python -m modal run modal/phase1.py::fit \
  --observer /weights/observer --performer /weights/performer --version qwen-bf16 \
  --bf16 --validation --pair-family Qwen2.5-7B --limit 16
```

The Modal fit uses the same corpus cache, volume and training entry point. Use `--limit` to set the per-class reservoir size. Evaluate the chosen fitted artifact on the test cohort with `--model-in`. For a release run, copy the Metal trace and fitted artifact to CUDA. Supply `--compare-trace`, `--reference-report`, `--bakeoff-report`, `--load-report` and `--enforce` to the Deep evaluator. Pass `--previous` when comparing with a previous Deep release. Missing evidence keeps the release ineligible. Parity compares numeric outcomes and UTF-16 sentence offsets for at least 200 identical documents. The methodology page reads the release's aggregate `eval/reports/phase-1/report.json`. Raw research texts stay in the corpus cache.

A partial bake-off can publish measured Metal candidates while CUDA is unavailable. It returns no selected model, sets `pass` to false and lists missing precision/backend measurements. Include `--rank-provisional` for a separate ordering of the measured candidates that meet the memory and ESL limits.

```sh
uv run vibechecker-eval bakeoff eval/reports/qwen-4/report.json \
  --partial --rank-provisional --out eval/artifacts/bakeoff-partial.json
```

If a candidate was rejected before scoring, record the preflight with `vibechecker-eval memory-preflight --pair-family FAMILY --bits 8 --observed-pid PID --basis "M6 candidate after loading both checkpoints" --out preflight.json` while its process is alive. Alternatively, pass `--projected-bytes BYTES` and give the calculation and its inputs in `--basis`. The command accepts values above 18 GiB. Include the file via `--rejected preflight.json` in either a full or partial bake-off. The report lists documented exclusions and their basis under `preflight_rejections`. Precisions awaiting evidence appear under `missing_measurements`.

```sh
uv run vibechecker-eval bakeoff eval/reports/{qwen-bf16,qwen-4,qwen-6}/report.json \
  --rejected eval/reports/phase-1/8bit-memory-preflight.json --out eval/artifacts/bakeoff.json
```

## Refit the Deep stacker with frozen heads

The original Deep model supplies checkpoint identities, source order and the fitted sentence, E7 and caution heads. Set the same checkpoint paths used by Deep, including `VIBECHECKER_ENCODER`. The M6 run used Metal with a 512-token Quick prefill. Each probe reads 769-value encoder vectors keyed by document hash from a private SQLite cache. For a fresh cache, omit `--cached-only` on the first command to extract the vectors.

```sh
export VIBECHECKER_BACKEND=mlx-metal
export VIBECHECKER_QUICK_PREFILL=512

uv run python -m vibechecker_eval.encoder_probe --candidate canonical --cached-only \
  --datasets raid raid-attacks asap ellipse liang --cache eval/.cache --seed 42 \
  --human-cap 1200 --clean-cap 320 --attack-cap 64 --features eval/artifacts/encoder.sqlite \
  --model-out eval/artifacts/encoder-canonical-guarded-v1.joblib --report eval/artifacts/encoder-canonical-guarded-v1.json

uv run python -m vibechecker_eval.encoder_probe --candidate svm-c16 --cached-only \
  --datasets raid raid-attacks asap ellipse liang --cache eval/.cache --seed 42 \
  --human-cap 1200 --clean-cap 320 --attack-cap 64 --features eval/artifacts/encoder.sqlite \
  --model-out eval/artifacts/encoder-svm-c16-guarded-v1.joblib --report eval/artifacts/encoder-svm-c16-guarded-v1.json

uv run python -m vibechecker_eval.encoder_probe --candidate logistic-c0.1 \
  --datasets raid raid-attacks asap ellipse liang --cache eval/.cache --seed 42 \
  --human-cap 2400 --clean-cap 640 --attack-cap 128 --features eval/artifacts/encoder.sqlite \
  --model-out eval/artifacts/encoder-logistic-expanded-guarded-fixed-v1.joblib \
  --report eval/artifacts/encoder-logistic-expanded-guarded-fixed-v1.json
```

All three probes fit on head fold 0 of the training partition. The canonical run selects among linear and approximate RBF candidates on an inner source-separated development fold. The exact RBF SVM uses `C=16` and fits a sigmoid to out-of-fold margins from three source-group folds. Each fold fits its own scaling, PCA and SVM, keeping all variations of a source together. The third run fixes logistic regularization at `C=0.1` and doubles the sampling caps. It reuses existing vectors and extracts only the additional documents. Use `--cached-only` once that expanded cache is complete.

The separate Deep cache holds numeric document features, labels, word counts, hashed document/source/stratum identifiers and the optional encoder vectors. Its metadata records dataset coverage, checkpoint digests, the runtime profile and the selection digest.

```sh
uv run vibechecker-eval deep-cache --model-in eval/artifacts/phase-1/deep-qwen7b-q4-p512-v1.joblib \
  --features eval/artifacts/frozen-features.sqlite --cache eval/.cache \
  --datasets raid raid-attacks asap ellipse liang --seed 42 --limit-per-class 96 \
  --train-limit-per-class 160 --cal-limit-per-class 352 --attack-limit-per-class 128

uv run vibechecker-eval deep-refit --model-in eval/artifacts/phase-1/deep-qwen7b-q4-p512-v1.joblib \
  --cache eval/.cache --features eval/artifacts/frozen-features.sqlite --probe eval/artifacts/encoder-canonical-guarded-v1.joblib \
  --model-out eval/artifacts/selected.joblib --selection-out eval/artifacts/validation-selection.json
```

Each accepted document or refusal commits separately. Rerun the same cache command to continue after interruption. A changed sampling plan, model, corpus or numerical profile needs a separate cache path. Omit `--probe` for a stacker-only comparison. Use `--without-encoder-vectors` when building a cache intended only for that comparison. The CPU refit reads the completed cache and the original artifact. Both commands accept `--commercial-only` and verify the original licensing scope.

Repeat `--probe` to compare independently trained encoder probes in one CPU run on the same cache.

```sh
uv run vibechecker-eval deep-refit --model-in eval/artifacts/phase-1/deep-qwen7b-q4-p512-v1.joblib \
  --cache eval/.cache --features eval/artifacts/frozen-features.sqlite \
  --probe eval/artifacts/encoder-canonical-guarded-v1.joblib --probe eval/artifacts/encoder-svm-c16-guarded-v1.joblib \
  --probe eval/artifacts/encoder-logistic-expanded-guarded-fixed-v1.joblib \
  --model-out eval/artifacts/selected.joblib --selection-out eval/artifacts/validation-selection.json
```

The parent and two stacker-only candidates are evaluated once. Each unique probe artifact adds four candidates and shares its cached probabilities across those fits. The report groups them by probe SHA-256, includes training provenance and the best admissible candidate for each probe, and records the validation document digest and gate-relative error for every candidate. A different scored document set invalidates the comparison.

Training uses fold 1 of the original training-source partition. Calibration uses the calibration partition. Each cap applies to one source and class. Training and calibration sample distinct source groups across generator/attack combinations. The attack cap limits the RAID attack shard in each fit partition. Mixed-role or label-conflicting document hashes and source groups shared with reserved partitions are excluded from fitting. The validation reservoir and generator grouping match `deep --cohort validation`. The final test fold is absent from the cache.

Each refit verifies the original corpus manifest and looks for normalized human passages assigned to several publisher groups across all splits and lengths. It removes the linked groups and their generated variants from its stacker training and calibration rows. The CPU runner preserves the input SQLite records and validation cohort. Both probe producers apply the same source-group quarantine to their training reservoir. Their saved provenance must match the refit's complete alias summary. The selection report records the source-alias digest and counts, document and group digests for excluded and effective fit rows, and the retained validation membership. The original heads remain frozen; their source overlap with held-out groups requires a separate audit of the original fit.

Each candidate retains the original eight displayed signals. The base candidates vary gradient-boosting complexity. Optional probe candidates append the probability from an independently fitted frozen-encoder probe. Two candidates assign a fixed weight of 0.50 or 0.75 to its log-odds before fitting the balanced-prior isotonic and 200 bootstrap calibrators. During refit, the probe and Deep cache must identify the same extraction backend, complete encoder files, prefill profile, representation version, dataset manifest and reserved head-training fold. The fitted model can then be evaluated across backends for parity.

The selection report identifies the parent and winner by SHA-256 and records each candidate’s settings, document metrics, worst stratum and gate results. Selection requires improvement in both validation ECE measures and preservation of other passing quality gates. Among qualifying candidates it minimizes the larger error relative to the 0.05 pooled and 0.08 stratum gates. If none qualifies, the output is an exact copy of the parent. Use `deep --model-in eval/artifacts/selected.joblib --cohort test` with the original final-test seed, limits and dataset order to produce the independent scorecard.

## Prospective final audit

The [frozen reservation](reports/phase-1/prospective-audit-reservation.json) contains 512 opaque document/source pairs, one per independent component, drawn from 16,711 length-eligible candidates. The reservation reconstructs the full historical 266-document envelope from its pinned corpus. It excludes every group in that envelope, every training, calibration and validation group, all groups linked by duplicate normalized text at any length, and all known human source aliases. Sampling rotates across datasets and generator, attack and length strata. The resulting proportions describe this coverage sample. Language screening happens during inference, with each refusal retained in the report counts.

The 512 reserved documents include 131 ASAP essays, 131 ELLIPSE essays, 130 clean RAID passages and 120 attacked RAID passages. No Liang group remained eligible after the exclusions. The audit can measure pooled discrimination and essay false positives. Generated-essay discrimination requires additional independent sources.

Reproduce the reservation on CPU without loading a detector.

```sh
uv run python -m vibechecker_eval.prospective --cache eval/.cache \
  --historical-audit eval/reports/phase-1/expanded-source-membership.json \
  --out eval/artifacts/prospective-audit-reservation.json
```

After model selection is complete, record the candidate SHA-256 and use a separate report version. The normal Deep evaluator applies the serving predictor, sentence metrics, unchanged quality gates and the frozen plan. The canonical plan digest below covers the complete JSON contents independent of indentation.

```sh
VIBECHECKER_QUICK_PREFILL=512 uv run vibechecker-eval deep --cohort prospective \
  --datasets raid raid-attacks asap ellipse liang --cache eval/.cache --seed 42 \
  --model-in "$frozen_model" --audit-model-sha256 "$frozen_model_sha256" \
  --audit-plan eval/reports/phase-1/prospective-audit-reservation.json \
  --audit-plan-sha256 98e100bdc12a14cefbe35c88f6b48397577e4f11388978c007dbdea6aabaf170 \
  --version "$prospective_version" --pair-family Qwen2.5-7B
```

## Paired rewrite stacker refit

The research-only rewrite experiment links rewritten human and machine text to their publisher originals in books and news. Its sidecar stores the 13 frozen document features and the 769-value encoder representation for each rewrite. SQLite rows commit independently. A refusal removes the whole pair from fitting or stress evaluation. The original Deep cache supplies the ordinary stacker and calibration rows and all 268 live validation documents.

The following commands use the Phase 1 verification checkout's artifact layout. Set the original Metal checkpoint paths and a 512-token Quick prefill. The CPU plan verifies the signed projection, original input manifest, frozen heads, v2 artifact, original numeric cache and protected document/source membership before selecting up to 48 groups per domain and role.

```sh
set -- --parent deep-qwen7b-q4-p512-v1.joblib --incumbent deep-qwen7b-q4-p512-v2.joblib \
  --incumbent-selection calibration-v2/selection.json --features calibration-v2/stack.sqlite \
  --cache ../eval/.cache --prospective-plan prospective-audit/reservation-v1.json \
  --supplement calibration-v2/rewrite-origin-v1/verified-cohort.sqlite \
  --supplement-sha256 5ab5814717ef46f5fc9f849704503fe49f5434a479e0970911a81339e94a00df \
  --sidecar calibration-v3/rewrite-stack.sqlite --groups-per-domain 48 --seed 42
python -m vibechecker_eval.rewrite_refit plan "$@"
python -m vibechecker_eval.rewrite_refit collect "$@"
python -m vibechecker_eval.rewrite_refit fit "$@" \
  --probe calibration-v3/rewrite-probe-v1/origin-probe-v1.joblib \
  --probe-sha256 f091eed2f254fdd5285ec8cf6ee595b93539d7207eac8b34da2972be173099b9 \
  --probe-study eval/reports/phase-1/rewrite-origin-probe.json \
  --probe-membership eval/reports/phase-1/rewrite-origin-membership.json \
  --band-controls calibration-v3/human-controls.sqlite --band-controls-sha256 "$controls_sha256" \
  --model-out calibration-v3/selected.joblib --selection-out calibration-v3/selection.json
```

The fit always compares the incumbent and two ordinary-probe controls trained with the same additional data. Each independently qualified rewrite probe adds its two fixed candidates and requires its preregistered SHA-256. Each seven-leaf stacker uses a 0.50 or 0.75 probe-logit weight, balanced-prior isotonic calibration and 200 bootstrap curves. A separate human calibration set determines its high-band cutoff. The report retains source and document digests, group shortfalls, all stress results by domain and origin, paired wins and ties, Brier and log loss, and ordinary-validation sensitivity before and after cutoff calibration.

A candidate must preserve the incumbent's passing primary gates, lower its worst primary calibration error, reduce matched-rewrite Brier error, increase within-source concordance and preserve pooled rewrite AUROC. The high band must retain at least 90% of ordinary machine hits against both the pre-control cutoff and the incumbent. Among admissible candidates the fit prioritizes passing both primary calibration limits, then the worst gate-relative error. If none qualifies, it emits a byte-identical copy of v2.

The `verify` subcommand takes the same shared inputs, plus `--model-in`, `--model-sha256`, `--selection-in`, `--selection-sha256`, `--band-controls` and `--out`. It compares individual serving indexes with the selection on primary validation and matched stress data. After recording the model and selection digests in version control, run it with `--withheld-specificity` and a separate output path to measure high-band false positives on the reserved RAID and PERSUADE controls.
