# qwen-6bit-v1

Deep runtime scored eligible held-out English documents. Hewlett is the US comparison cohort. TOEFL estimates cover eligible essays only.

Backend `mlx-metal`. Scored 54 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 54 | 0.9390 | 0.6111 | 0.1233 | 0.0996 | 0.0278 (0.0049, 0.1417) |
| attack/none | 50 | 0.9286 | 0.5714 | 0.1452 | 0.1003 | 0.0278 (0.0049, 0.1417) |
| attack/paraphrase | 1 | — | — | 0.6000 | 0.3600 | — |
| attack/perplexity_misspelling | 2 | — | — | 0.0000 | 0.0000 | — |
| attack/synonym | 1 | — | — | 0.0000 | 0.0000 | — |
| dataset/asap | 6 | — | — | 0.0750 | 0.0338 | 0.1667 (0.0301, 0.5635) |
| dataset/ellipse | 8 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.3244) |
| dataset/liang/college-ai | 5 | — | — | 0.2560 | 0.1638 | — |
| dataset/liang/college-human | 9 | — | — | 0.1333 | 0.0533 | 0.0000 (0.0000, 0.2991) |
| dataset/liang/hewlett | 8 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.3244) |
| dataset/raid | 14 | 0.8222 | 0.5556 | 0.3093 | 0.2511 | 0.0000 (0.0000, 0.4345) |
| dataset/raid-attacks | 4 | — | — | 0.1500 | 0.0900 | — |
| fairness/ESL-essay | 9 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.2991) |
| generator/cohere | 1 | — | — | 0.6400 | 0.4096 | — |
| generator/gpt-3 | 5 | — | — | 0.2560 | 0.1638 | — |
| generator/gpt2 | 3 | — | — | 0.3300 | 0.3267 | — |
| generator/gpt4 | 1 | — | — | 0.0000 | 0.0000 | — |
| generator/human | 36 | — | — | 0.0681 | 0.0278 | 0.0278 (0.0049, 0.1417) |
| generator/llama-chat | 2 | — | — | 0.3000 | 0.1800 | — |
| generator/mistral | 3 | — | — | 0.3100 | 0.2883 | — |
| generator/mpt | 3 | — | — | 0.3233 | 0.3136 | — |
| genre/essay | 36 | 0.9484 | 0.6000 | 0.0814 | 0.0417 | 0.0323 (0.0057, 0.1619) |
| genre/other | 18 | 0.8615 | 0.6154 | 0.2072 | 0.2153 | 0.0000 (0.0000, 0.4345) |
| length/300-599 | 46 | 0.9474 | 0.6111 | 0.1274 | 0.1099 | 0.0357 (0.0063, 0.1771) |
| length/600-1199 | 8 | — | — | 0.1000 | 0.0400 | 0.0000 (0.0000, 0.3244) |
| split/test | 54 | 0.9390 | 0.6111 | 0.1233 | 0.0996 | 0.0278 (0.0049, 0.1417) |
| writer/ESL | 9 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.2991) |
| writer/native_proxy | 8 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.3244) |
| writer/unknown | 37 | 0.8845 | 0.6111 | 0.1800 | 0.1453 | 0.0526 (0.0094, 0.2464) |

## Deep acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | 0.9484 | 0.9 | pass |
| pooled_ece | 0.1233 | 0.05 | fail |
| worst_stratum_ece | 0.6400 | 0.08 | fail |
| human_essay_high_fpr | 0.0323 | 0.02 | fail |
| esl_high_fpr | 0.0000 | 0.05 | pass |
| toefl_high_fpr | — | 0.05 | unmeasured |
| esl_native_gap | 0.0000 | 0.03 | pass |
| toefl_native_gap | — | 0.03 | unmeasured |

## Sampling

Training used seed 42 and a reservoir limit of 16 per class, dataset and split (zero means all rows). Dataset order was raid, raid-attacks, asap, ellipse, liang.
Evaluation used seed 42 and a reservoir limit of 16 on the validation cohort.
The Quick LM used 64 tokens per prefill during evaluation.

## Sentence and hardware evidence

Mixed-document F1 was 0.7553 across 297 held-out sentences.
Metal/CUDA parity: unmeasured.
Release eligible: False.

- falcon_reference: unmeasured
- quantization: unmeasured
- m6_load: unmeasured

The length gate excluded 91 TOEFL essays. A cohort with no eligible essays has no estimated false-positive rate.

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.
