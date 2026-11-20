# Phase 0 evaluation

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
