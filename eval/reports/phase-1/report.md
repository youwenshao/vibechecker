# deep-qwen7b-q4-p512-v2

Deep runtime scored eligible held-out English documents. Hewlett is the US comparison cohort. TOEFL estimates cover eligible essays only.

Backend `mlx-metal`. Scored 221 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 221 | 0.9933 | 0.0000 | 0.0211 | 0.0148 | 0.0263 (0.0103, 0.0657) |
| attack/alternative_spelling | 6 | — | — | 0.0000 | 0.0000 | — |
| attack/article_deletion | 3 | — | — | 0.0000 | 0.0000 | — |
| attack/homoglyph | 2 | — | — | 0.0000 | 0.0000 | — |
| attack/none | 196 | 0.9966 | 1.0000 | 0.0187 | 0.0116 | 0.0199 (0.0068, 0.0568) |
| attack/number | 1 | — | — | 0.0000 | 0.0000 | — |
| attack/paraphrase | 4 | 0.5000 | 0.0000 | 0.2500 | 0.2500 | 1.0000 (0.2065, 1.0000) |
| attack/perplexity_misspelling | 3 | — | — | 0.0000 | 0.0000 | — |
| attack/synonym | 6 | — | — | 0.0000 | 0.0000 | — |
| dataset/asap | 26 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1287) |
| dataset/ellipse | 29 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1170) |
| dataset/liang/college-ai | 5 | — | — | 0.0000 | 0.0000 | — |
| dataset/liang/college-human | 36 | — | — | 0.0875 | 0.0610 | 0.0833 (0.0287, 0.2183) |
| dataset/liang/hewlett | 24 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1380) |
| dataset/raid | 76 | 1.0000 | 1.0000 | 0.0068 | 0.0010 | 0.0000 (0.0000, 0.0964) |
| dataset/raid-attacks | 25 | 0.5000 | 0.0000 | 0.0400 | 0.0400 | 1.0000 (0.2065, 1.0000) |
| fairness/ESL-essay | 32 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1072) |
| generator/chatgpt | 2 | — | — | 0.0000 | 0.0000 | — |
| generator/cohere | 4 | — | — | 0.0475 | 0.0090 | — |
| generator/gpt-3 | 5 | — | — | 0.0000 | 0.0000 | — |
| generator/gpt2 | 16 | — | — | 0.0000 | 0.0000 | — |
| generator/gpt4 | 2 | — | — | 0.0000 | 0.0000 | — |
| generator/human | 152 | — | — | 0.0295 | 0.0213 | 0.0263 (0.0103, 0.0657) |
| generator/llama-chat | 7 | — | — | 0.0000 | 0.0000 | — |
| generator/mistral | 10 | — | — | 0.0000 | 0.0000 | — |
| generator/mistral-chat | 5 | — | — | 0.0000 | 0.0000 | — |
| generator/mpt | 14 | — | — | 0.0000 | 0.0000 | — |
| generator/mpt-chat | 4 | — | — | 0.0000 | 0.0000 | — |
| genre/essay | 120 | 0.9957 | 1.0000 | 0.0262 | 0.0183 | 0.0261 (0.0089, 0.0739) |
| genre/other | 101 | 0.9863 | 0.0000 | 0.0150 | 0.0106 | 0.0270 (0.0048, 0.1382) |
| length/1200+ | 1 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.7935) |
| length/300-599 | 179 | 0.9954 | 1.0000 | 0.0134 | 0.0094 | 0.0182 (0.0050, 0.0639) |
| length/600-1199 | 41 | — | — | 0.0554 | 0.0388 | 0.0488 (0.0135, 0.1614) |
| split/test | 221 | 0.9933 | 0.0000 | 0.0211 | 0.0148 | 0.0263 (0.0103, 0.0657) |
| writer/ESL | 32 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1072) |
| writer/native_proxy | 24 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1380) |
| writer/unknown | 165 | 0.9894 | 0.0000 | 0.0283 | 0.0198 | 0.0417 (0.0163, 0.1023) |

## Deep acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | 0.9957 | 0.9 | pass |
| pooled_ece | 0.0211 | 0.05 | pass |
| worst_stratum_ece | 0.2500 | 0.08 | fail |
| human_essay_high_fpr | 0.0261 | 0.02 | fail |
| esl_high_fpr | 0.0000 | 0.05 | pass |
| toefl_high_fpr | — | 0.05 | unmeasured |
| esl_native_gap | 0.0000 | 0.03 | pass |
| toefl_native_gap | — | 0.03 | unmeasured |
| max_metric_regression | 1.0000 | 0.01 | fail |
| sentence_f1_regression | 0.0000 | 0.01 | pass |

## Sampling

The refitted stacker used seed 42, a training limit of 160 and a calibration limit of 352 per source and class. Dataset order was raid, raid-attacks, asap, ellipse, liang.
Evaluation used seed 42 and a reservoir limit of 72 on the test cohort.
The Quick LM used 512 tokens per prefill during evaluation.
Regression checks compare the same cohort with `deep-qwen7b-q4-p512-v1` (report SHA-256 `96d87233fad04db751a747f030fdf0c83cc0e64a9b1d67d7abc7eb946afc63a6`).

## Sentence and hardware evidence

Mixed-document F1 was 0.6316 across 1132 held-out sentences.
Metal/CUDA parity: unmeasured.
Release eligible: False.

- falcon_reference: unmeasured
- quantization: incomplete
- m6_load: passed

The length gate excluded 91 TOEFL essays. A cohort with no eligible essays has no estimated false-positive rate.

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.
