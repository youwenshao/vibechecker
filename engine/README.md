# Phase 0 Quick engine

The service and the evaluation harness share `FeatureExtractor`, `QuickStacker` and `QuickEngine`. A Quick check requires 150–5,000 English words. The spaCy sentencizer processes NFC text with LF line endings. Sentence offsets refer to the exact original string in UTF-16 code units. Invisible characters and mixed Latin/Greek or Latin/Cyrillic words produce flags.

## Run on the M6

From the repository root, create a Python 3.12 environment, then install the Metal extra and fetch the pinned checkpoints.

```sh
uv venv --python 3.12 .venv
uv pip install -e './engine[metal,test]'
.venv/bin/python engine/tools/fetch_weights.py artifacts
export VIBECHECKER_LM="$PWD/artifacts/Qwen2.5-0.5B"
export VIBECHECKER_ENCODER="$PWD/artifacts/modernbert-ai-detection-raid-mage"
export VIBECHECKER_STACKER="$PWD/artifacts/quick.joblib"
export VIBECHECKER_BACKEND=mlx-metal
```

Fit the stacker using the registry-backed training command in the evaluation harness. Treat its joblib file as trusted executable input. Deploy the same fitted file and weight revisions to every backend. Use the `cpu` extra on Linux CPU and `cuda` on the CUDA 13 host. Model inference uses local files. The fetch tool checks the SHA-256 of each safetensors file after downloading.

```sh
.venv/bin/python -m pytest engine/tests
.venv/bin/vibechecker-benchmark path/to/public-1000-word-essay.txt --runs 20
```

The benchmark reports warm engine p50/p95 milliseconds. The service and browser add scheduling, streaming and network time.

The M6 Phase 0 measurement used 20 warmed calls on a 1,000-word public essay. Median engine latency was 622 ms and p95 was 625 ms. The CPU and Metal paths returned the same index and interval for that essay. The machine configuration, input selection, hashes and numeric comparisons are in [the benchmark record](benchmarks/m6-phase0.json).

## Read a Quick result

| Signal | Displayed value | Sparkline samples |
| --- | --- | --- |
| E1 | Document perplexity from mean next-token surprise | Per-sentence perplexity |
| E2 | Mean natural log of next-token rank | Consecutive token groups |
| E6 | AI-class probability from the ModernBERT detector, weighted by the number of content tokens in each 512-token window | Window probabilities |
| Stylometry | Distinct case-folded words divided by total words | Ratios within chunks of about 200 words |

The reference is the median of that feature across human training essays. Additional stacker inputs are sentence-surprise variability, entropy, average word length, sentence-length variability and highest word frequency. Sparkline series are reduced to at most 16 consecutive means. A single window or chunk has no trend line.

Held-out calibration uses isotonic regression at a balanced human/machine prior. A length bin gets a local curve at 1,000 calibration examples with both labels present. The interval spans the 5th–95th percentiles of 200 class-stratified bootstrap calibrators. Phase 0 uses provisional minimum widths of 20, 14, 10 and 8 index points for the ascending length bins. These widths communicate calibration uncertainty and do not establish a coverage guarantee.

The boundaries for mixed and high bands limit the observed human calibration-set false-positive rate to 20% and 2% respectively, accounting for ties after index rounding. The evaluation report checks performance separately on held-out essays. A detector score is a reason to look closer, never proof.
