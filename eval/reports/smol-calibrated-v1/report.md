# smol-calibrated-v1

Deep runtime scored eligible held-out English documents. Hewlett is the US comparison cohort. TOEFL estimates cover eligible essays only.

Backend `mlx-metal`. Scored 221 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 221 | 0.9633 | 0.9275 | 0.0296 | 0.0263 | 0.0000 (0.0000, 0.0246) |
| attack/alternative_spelling | 6 | — | — | 0.0000 | 0.0000 | — |
| attack/article_deletion | 3 | — | — | 0.0000 | 0.0000 | — |
| attack/homoglyph | 2 | — | — | 0.0000 | 0.0000 | — |
| attack/none | 196 | 0.9662 | 0.9333 | 0.0232 | 0.0195 | 0.0000 (0.0000, 0.0248) |
| attack/number | 1 | — | — | 0.0000 | 0.0000 | — |
| attack/paraphrase | 4 | 0.6667 | 0.3333 | 0.5000 | 0.5000 | 0.0000 (0.0000, 0.7935) |
| attack/perplexity_misspelling | 3 | — | — | 0.0000 | 0.0000 | — |
| attack/synonym | 6 | — | — | 0.0000 | 0.0000 | — |
| dataset/asap | 26 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1287) |
| dataset/ellipse | 29 | — | — | 0.0217 | 0.0137 | 0.0000 (0.0000, 0.1170) |
| dataset/liang/college-ai | 5 | — | — | 0.0000 | 0.0000 | — |
| dataset/liang/college-human | 36 | — | — | 0.0175 | 0.0110 | 0.0000 (0.0000, 0.0964) |
| dataset/liang/hewlett | 24 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1380) |
| dataset/raid | 76 | 0.9625 | 0.9250 | 0.0433 | 0.0398 | 0.0000 (0.0000, 0.0964) |
| dataset/raid-attacks | 25 | 0.9583 | 0.9167 | 0.0800 | 0.0800 | 0.0000 (0.0000, 0.7935) |
| fairness/ESL-essay | 32 | — | — | 0.0197 | 0.0124 | 0.0000 (0.0000, 0.1072) |
| generator/chatgpt | 2 | — | — | 0.0000 | 0.0000 | — |
| generator/cohere | 4 | — | — | 0.5200 | 0.5016 | — |
| generator/gpt-3 | 5 | — | — | 0.0000 | 0.0000 | — |
| generator/gpt2 | 16 | — | — | 0.0050 | 0.0004 | — |
| generator/gpt4 | 2 | — | — | 0.0000 | 0.0000 | — |
| generator/human | 152 | — | — | 0.0083 | 0.0052 | 0.0000 (0.0000, 0.0246) |
| generator/llama-chat | 7 | — | — | 0.0000 | 0.0000 | — |
| generator/mistral | 10 | — | — | 0.1080 | 0.1006 | — |
| generator/mistral-chat | 5 | — | — | 0.0000 | 0.0000 | — |
| generator/mpt | 14 | — | — | 0.1464 | 0.1430 | — |
| generator/mpt-chat | 4 | — | — | 0.0000 | 0.0000 | — |
| genre/essay | 120 | 1.0000 | 1.0000 | 0.0105 | 0.0066 | 0.0000 (0.0000, 0.0323) |
| genre/other | 101 | 0.9609 | 0.9219 | 0.0524 | 0.0497 | 0.0000 (0.0000, 0.0941) |
| length/1200+ | 1 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.7935) |
| length/300-599 | 179 | 0.9631 | 0.9275 | 0.0366 | 0.0325 | 0.0000 (0.0000, 0.0337) |
| length/600-1199 | 41 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.0857) |
| split/test | 221 | 0.9633 | 0.9275 | 0.0296 | 0.0263 | 0.0000 (0.0000, 0.0246) |
| writer/ESL | 32 | — | — | 0.0197 | 0.0124 | 0.0000 (0.0000, 0.1072) |
| writer/native_proxy | 24 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1380) |
| writer/unknown | 165 | 0.9634 | 0.9275 | 0.0359 | 0.0328 | 0.0000 (0.0000, 0.0385) |

## Deep acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | 1.0000 | 0.9 | pass |
| pooled_ece | 0.0296 | 0.05 | pass |
| worst_stratum_ece | 0.5200 | 0.08 | fail |
| human_essay_high_fpr | 0.0000 | 0.02 | pass |
| esl_high_fpr | 0.0000 | 0.05 | pass |
| toefl_high_fpr | — | 0.05 | unmeasured |
| esl_native_gap | 0.0000 | 0.03 | pass |
| toefl_native_gap | — | 0.03 | unmeasured |

## Sampling

The fitted artifact has no recorded training selection.
Evaluation used seed 42 and a reservoir limit of 72 on the test cohort.
The Quick LM used 64 tokens per prefill during evaluation.

## Sentence and hardware evidence

Mixed-document F1 was 0.6241 across 1132 held-out sentences.
Metal/CUDA parity: unmeasured.
Release eligible: False.

- falcon_reference: unmeasured
- quantization: unmeasured
- m6_load: failed

The length gate excluded 91 TOEFL essays. A cohort with no eligible essays has no estimated false-positive rate.

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.
