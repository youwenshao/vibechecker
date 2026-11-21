# Paired rewrite sources for the Phase 1 calibration study

This research cohort contains 560 source groups and 2,240 documents. Each group contributes a paraphrased human passage, a paraphrased model generation on the same prompt, and their two clean parents. All four pass the production English and 300–2,500-word Deep admission checks. The model input consists of text. Publisher origin labels and source links are used for fitting and evaluation. [Prespecified fit and comparison](rewrite-calibration-protocol.md) · [Pinned cohort manifest](../../src/vibechecker_eval/rewrite_manifest.json)

| Domain | Head training pairs | Stacker training pairs | Calibration pairs | Stress-validation pairs |
| --- | ---: | ---: | ---: | ---: |
| Books | 120 | 64 | 64 | 32 |
| News | 120 | 64 | 64 | 32 |

RAID applies the DIPPER-11B paraphraser to both kinds of source. The publisher's transformation code retains the original model field, including `human`. Its evaluator uses these human-origin rows as negative examples for AUROC and uses clean human rows to set the false-positive threshold. Here, `adv_source_id` identifies the exact clean parent and `source_id` identifies the shared human source. The dataset card lists MIT. Underlying source rights vary and the project restricts these inputs to research. [RAID paper, Appendix E](https://aclanthology.org/2024.acl-long.674.pdf) · [Publisher dataset card](https://huggingface.co/datasets/liamdugan/raid/blob/main/README.md) · [Transformation code](https://github.com/liamdugan/raid/blob/84c2ea413752a39def012394a0ce905c8a692b05/generation/adversarial/pipeline.py#L9-L24) · [Evaluation code](https://github.com/liamdugan/raid/blob/84c2ea413752a39def012394a0ce905c8a692b05/raid/evaluate.py#L94-L165) · [Project source review](../../LICENSES.md)

The original attack shard contains abstract paraphrases. Its head-training fold has 536 human-origin rewrites below 300 words and zero admissible human-origin rewrites. Among length- and language-eligible source-matched pairs it offers zero head pairs, one stacker pair and one calibration pair. A read of the release's Parquet metadata located additional book and news paraphrases in the same pinned public training conversion. The build verifies both complete shard files against their SHA-256 before projecting the inclusive row groups below. Together the files contain 509,771,969 bytes. [Books shard](https://huggingface.co/datasets/liamdugan/raid/resolve/5008b2d167f74bfd4ceff6b3b0512b7097d7cbb1/raid/partial-train/0003.parquet) · [News shard](https://huggingface.co/datasets/liamdugan/raid/resolve/5008b2d167f74bfd4ceff6b3b0512b7097d7cbb1/raid/partial-train/0006.parquet)

| Domain | Shard | Zero-based row groups | Required attack |
| --- | --- | --- | --- |
| Books | 0003 | 87–110 | paraphrase |
| News | 0006 | 125–148 | paraphrase |

The builder hashes the full original five-dataset corpus, PERSUADE controls and both supplemental shards. Of 873,746 distinct normalized document hashes and 42,297 source IDs, 186 connected components contained multiple source IDs. The cohort admits one group per singleton component and excludes conflicting origin labels. Stress-validation draws from previously unused stack-training sources. Every selected role was disjoint from the 266-document historical envelope, 512-document prospective reservation and original validation documents. [Isolation counts and group digests](../../src/vibechecker_eval/rewrite_manifest.json)

The cohort covers two English domains, six source generators and one automated paraphraser. It supports paired origin comparisons in the Deep input range. Short inputs, essays, other languages, other rewrite systems and the prevalence of AI-assisted editing require separate evidence.

## Reproduce the cohort

From the repository root, supply the authenticated 2,606-row feature cache used by the original Phase 1 refit. The CPU builder retrieves missing source files into the research cache and validates the resulting projection against the checked-in manifest. [Feature-cache recipe](../../README.md) · [Frozen reservation](prospective-audit-reservation.json)

```sh
uv run python -m vibechecker_eval.rewrite_data \
  --cache eval/.cache \
  --stack-db eval/artifacts/frozen-features.sqlite \
  --reservation eval/reports/phase-1/prospective-audit-reservation.json \
  --output eval/artifacts/rewrite-origin.sqlite
```

The projection digest is `1558a0004e629dd4e670c05a4584d726e71e95ac41af2c2d6245b0a3c7aafeac`. It binds exact document bytes, normalized IDs, parent links and role assignments independently of SQLite layout.
