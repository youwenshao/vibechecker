# deep-qwen7b-q4-p512-v4

Deep runtime scored eligible held-out English documents. Hewlett is the US comparison cohort. TOEFL estimates cover eligible essays only.

Backend `mlx-metal`. Scored 221 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 221 | 0.9991 | 1.0000 | 0.0229 | 0.0155 | 0.0526 (0.0269, 0.1004) |
| attack/alternative_spelling | 6 | — | — | 0.0000 | 0.0000 | — |
| attack/article_deletion | 3 | — | — | 0.0000 | 0.0000 | — |
| attack/homoglyph | 2 | — | — | 0.0000 | 0.0000 | — |
| attack/none | 196 | 0.9993 | 1.0000 | 0.0240 | 0.0158 | 0.0464 (0.0226, 0.0926) |
| attack/number | 1 | — | — | 0.0000 | 0.0000 | — |
| attack/paraphrase | 4 | 1.0000 | 1.0000 | 0.1800 | 0.0831 | 1.0000 (0.2065, 1.0000) |
| attack/perplexity_misspelling | 3 | — | — | 0.0000 | 0.0000 | — |
| attack/synonym | 6 | — | — | 0.0083 | 0.0004 | — |
| dataset/asap | 26 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1287) |
| dataset/ellipse | 29 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1170) |
| dataset/liang/college-ai | 5 | — | — | 0.0000 | 0.0000 | — |
| dataset/liang/college-human | 36 | — | — | 0.1197 | 0.0761 | 0.1667 (0.0787, 0.3189) |
| dataset/liang/hewlett | 24 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1380) |
| dataset/raid | 76 | 1.0000 | 1.0000 | 0.0130 | 0.0047 | 0.0278 (0.0049, 0.1417) |
| dataset/raid-attacks | 25 | 1.0000 | 1.0000 | 0.0308 | 0.0134 | 1.0000 (0.2065, 1.0000) |
| fairness/ESL-essay | 32 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1072) |
| generator/chatgpt | 2 | — | — | 0.0000 | 0.0000 | — |
| generator/cohere | 4 | — | — | 0.0250 | 0.0013 | — |
| generator/gpt-3 | 5 | — | — | 0.0000 | 0.0000 | — |
| generator/gpt2 | 16 | — | — | 0.0100 | 0.0006 | — |
| generator/gpt4 | 2 | — | — | 0.0000 | 0.0000 | — |
| generator/human | 152 | — | — | 0.0366 | 0.0224 | 0.0526 (0.0269, 0.1004) |
| generator/llama-chat | 7 | — | — | 0.0071 | 0.0004 | — |
| generator/mistral | 10 | — | — | 0.0050 | 0.0003 | — |
| generator/mistral-chat | 5 | — | — | 0.0000 | 0.0000 | — |
| generator/mpt | 14 | — | — | 0.0100 | 0.0005 | — |
| generator/mpt-chat | 4 | — | — | 0.0000 | 0.0000 | — |
| genre/essay | 120 | 1.0000 | 1.0000 | 0.0359 | 0.0228 | 0.0522 (0.0241, 0.1092) |
| genre/other | 101 | 1.0000 | 1.0000 | 0.0174 | 0.0068 | 0.0541 (0.0150, 0.1770) |
| length/1200+ | 1 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.7935) |
| length/300-599 | 179 | 1.0000 | 1.0000 | 0.0155 | 0.0074 | 0.0364 (0.0142, 0.0898) |
| length/600-1199 | 41 | — | — | 0.0802 | 0.0514 | 0.0976 (0.0386, 0.2255) |
| split/test | 221 | 0.9991 | 1.0000 | 0.0229 | 0.0155 | 0.0526 (0.0269, 0.1004) |
| writer/ESL | 32 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1072) |
| writer/native_proxy | 24 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1380) |
| writer/unknown | 165 | 0.9986 | 0.8551 | 0.0307 | 0.0208 | 0.0833 (0.0428, 0.1559) |

## Deep acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | 1.0000 | 0.9 | pass |
| pooled_ece | 0.0229 | 0.05 | pass |
| worst_stratum_ece | 0.1800 | 0.08 | fail |
| human_essay_high_fpr | 0.0522 | 0.02 | fail |
| esl_high_fpr | 0.0000 | 0.05 | pass |
| toefl_high_fpr | — | 0.05 | unmeasured |
| esl_native_gap | 0.0000 | 0.03 | pass |
| toefl_native_gap | — | 0.03 | unmeasured |
| max_metric_regression | 0.1220 | 0.01 | fail |
| sentence_f1_regression | 0.0000 | 0.01 | pass |

## Sampling

The refitted stacker used seed 42, a training limit of 160 and a calibration limit of 352 per source and class. Dataset order was raid, raid-attacks, asap, ellipse, liang.
Evaluation used seed 42 and a reservoir limit of 72 on the test cohort.
The Quick LM used 512 tokens per prefill during evaluation.
Regression checks compare the same cohort with `deep-qwen7b-q4-p512-v2` (report SHA-256 `00c495a03a07dc3df2d7ecebca55b1934f30c254711556542adbf0953cdb7d9f`).

## Sentence and hardware evidence

Mixed-document F1 was 0.6316 across 1132 held-out sentences.
Metal/CUDA parity: unmeasured.
Release eligible: False.

- falcon_reference: unmeasured
- quantization: incomplete
- m6_load: passed

The length gate excluded 91 TOEFL essays. A cohort with no eligible essays has no estimated false-positive rate.

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.

The [Phase 1.1 blocker report](phase-1.1/report.md) evaluates frozen subgroup cutoffs, admissions coverage and all 91 short TOEFL records.
