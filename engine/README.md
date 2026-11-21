# VibeChecker inference engine

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

The default Quick prefill processes 64 tokens at a time. For the M6 throughput comparison, run the benchmark with `--compare-prefill 256` on a public fixture. It times the baseline and candidate on the same loaded models, prints absolute differences for all nine input features, and checks the displayed index, band and interval. The candidate compiles the existing MLX reduction formulas and batches up to two equal-length encoder windows. Set `VIBECHECKER_QUICK_PREFILL` on the load-test service to exercise that token count under concurrency.

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

## Deep inference

Deep accepts 300–2,500 English words. Set `VIBECHECKER_PAIR_OBSERVER` to the base model directory, `VIBECHECKER_PAIR_PERFORMER` to the matching instruct checkpoint, and `VIBECHECKER_DEEP_MODEL` to the fitted Deep joblib. The fitted file binds SHA-256 digests of the four checkpoints and their tokenizer and configuration files. Startup verifies those bytes on each host. Only deployment-controlled files should be loaded. The MLX reader supports the original rotary multi-query Falcon-7B architecture alongside the model families provided by mlx-lm.

`PairExtractor.score(text, max_tokens=512)` implements the paper-comparison path. Production scoring uses the full accepted essay. Both compute observed performer log probabilities and first and second moments under the observer distribution from the same two passes. Binoculars uses every non-padding context in its denominator, including the final context. Analytic Fast-DetectGPT compares the observed log likelihood to the expected sum and its standard deviation at positions with known targets. The numerical goldens in `tests/test_deep.py` were obtained by running the published functions on the fixed logits in that test. [Binoculars metrics](https://github.com/ahans30/Binoculars/blob/c8ae2f90d50ee696418bc71d8d9e5020e5f9d7b8/binoculars/metrics.py) · [Fast-DetectGPT analytic criterion](https://github.com/baoguangsheng/fast-detect-gpt/blob/971b05202bac2bb504d60c0ac0812fea7a8f7c82/scripts/fast_detect_gpt.py)

CI runs a CPU smoke check through the same pair reader with the pinned SmolLM2-135M base and instruct checkpoints. To repeat it on Linux with the CPU extra installed, run `python engine/tools/smoke_smol.py`. The first run downloads both checkpoints and verifies the weight hashes. Later runs can use `HF_HUB_OFFLINE=1` with the populated cache.

Each request owns two KV caches. Once the pair finishes a chunk, the learned attention head scores its sentences and emits their UTF-16 spans. The tooltip names the sentence head when its score reaches 0.5 and highlights sentence-level discrepancy or cross-entropy ratios beyond the corresponding human training deciles. A sentence with no observed tokens has a neutral 0.5 marker and no signal attributions. The Ghostbuster-style logistic head combines the two models' token likelihoods, their difference and covariance, and small-LM summaries. A separate pair of supervised heads adds contextual warnings. An ESL warning expands each end of the document interval by up to five points within the 0–100 range.

The frozen ModernBERT checkpoint has 22 encoder layers, a hidden width of 768, mean pooling and a GELU classification head. Its model card computes the machine score from softmax column 1. [Pinned configuration](https://huggingface.co/GeorgeDrayson/modernbert-ai-detection-raid-mage/blob/e047d9c56f51a7e5c5ef5b0dd556f519bb9dd624/config.json) � [Publisher's inference example](https://huggingface.co/GeorgeDrayson/modernbert-ai-detection-raid-mage/blob/e047d9c56f51a7e5c5ef5b0dd556f519bb9dd624/README.md)

An optional Deep probe reuses each 512-token encoder forward pass. `Encoder.evidence` collects the last hidden state's masked mean before the GELU head and the raw machine-minus-human logit margin. Both are averaged across windows using their content-token counts. `modernbert-window-mean-margin-v1` orders the resulting 769 fp32 values as 768 embedding coordinates followed by the margin. This preserves evidence of relative confidence when softmax scores round to the same value. Only Deep models fitted with the probe supply its supervised score to the stacker. The service's numerical wire result contains the existing E6 probability and omits the representation.

The Deep stacker fits its own human references, thresholds and 200 held-out bootstrap calibrators. The headline includes E1–E7 and stylometry. Training, scored cohorts and release gates belong to the evaluation harness.

To prepare a candidate for the quantization comparison, convert each member from the same unquantized source snapshot into a fresh directory. Record the source revisions and candidate hashes in the evaluation manifest.

```sh
python engine/tools/quantize_pair_member.py weights/base weights/base-q4 --bits 4
python engine/tools/quantize_pair_member.py weights/instruct weights/instruct-q4 --bits 4
```
