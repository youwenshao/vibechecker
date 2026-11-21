# deep-qwen7b-q4-p512-v1

Deep runtime scored eligible held-out English documents. Hewlett is the US comparison cohort. TOEFL estimates cover eligible essays only.

Backend `mlx-metal`. Scored 221 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 221 | 0.9325 | 0.7536 | 0.0801 | 0.0757 | 0.0000 (0.0000, 0.0246) |
| attack/alternative_spelling | 6 | — | — | 0.0133 | 0.0011 | — |
| attack/article_deletion | 3 | — | — | 0.1567 | 0.0528 | — |
| attack/homoglyph | 2 | — | — | 0.4550 | 0.2113 | — |
| attack/none | 196 | 0.9156 | 0.7111 | 0.0804 | 0.0702 | 0.0000 (0.0000, 0.0248) |
| attack/number | 1 | — | — | 0.0000 | 0.0000 | — |
| attack/paraphrase | 4 | 0.8333 | 0.6667 | 0.6250 | 0.5577 | 0.0000 (0.0000, 0.7935) |
| attack/perplexity_misspelling | 3 | — | — | 0.1300 | 0.0507 | — |
| attack/synonym | 6 | — | — | 0.0000 | 0.0000 | — |
| dataset/asap | 26 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.1287) |
| dataset/ellipse | 29 | — | — | 0.0003 | 0.0000 | 0.0000 (0.0000, 0.1170) |
| dataset/liang/college-ai | 5 | — | — | 0.0160 | 0.0013 | — |
| dataset/liang/college-human | 36 | — | — | 0.1467 | 0.0704 | 0.0000 (0.0000, 0.0964) |
| dataset/liang/hewlett | 24 | — | — | 0.0200 | 0.0096 | 0.0000 (0.0000, 0.1380) |
| dataset/raid | 76 | 0.8826 | 0.5000 | 0.1326 | 0.1446 | 0.0000 (0.0000, 0.0964) |
| dataset/raid-attacks | 25 | 0.9792 | 0.9583 | 0.1740 | 0.1188 | 0.0000 (0.0000, 0.7935) |
| fairness/ESL-essay | 32 | — | — | 0.0003 | 0.0000 | 0.0000 (0.0000, 0.1072) |
| generator/chatgpt | 2 | — | — | 0.0400 | 0.0032 | — |
| generator/cohere | 4 | — | — | 0.8300 | 0.7276 | — |
| generator/gpt-3 | 5 | — | — | 0.0160 | 0.0013 | — |
| generator/gpt2 | 16 | — | — | 0.3644 | 0.2715 | — |
| generator/gpt4 | 2 | — | — | 0.3000 | 0.1384 | — |
| generator/human | 152 | — | — | 0.0651 | 0.0333 | 0.0000 (0.0000, 0.0246) |
| generator/llama-chat | 7 | — | — | 0.1514 | 0.1381 | — |
| generator/mistral | 10 | — | — | 0.1080 | 0.1006 | — |
| generator/mistral-chat | 5 | — | — | 0.0160 | 0.0013 | — |
| generator/mpt | 14 | — | — | 0.1936 | 0.1421 | — |
| generator/mpt-chat | 4 | — | — | 0.1175 | 0.0396 | — |
| genre/essay | 120 | 1.0000 | 1.0000 | 0.0488 | 0.0231 | 0.0000 (0.0000, 0.0323) |
| genre/other | 101 | 0.9090 | 0.5469 | 0.1191 | 0.1382 | 0.0000 (0.0000, 0.0941) |
| length/1200+ | 1 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.7935) |
| length/300-599 | 179 | 0.9321 | 0.7536 | 0.0869 | 0.0867 | 0.0000 (0.0000, 0.0337) |
| length/600-1199 | 41 | — | — | 0.0646 | 0.0296 | 0.0000 (0.0000, 0.0857) |
| split/test | 221 | 0.9325 | 0.7536 | 0.0801 | 0.0757 | 0.0000 (0.0000, 0.0246) |
| writer/ESL | 32 | — | — | 0.0003 | 0.0000 | 0.0000 (0.0000, 0.1072) |
| writer/native_proxy | 24 | — | — | 0.0200 | 0.0096 | 0.0000 (0.0000, 0.1380) |
| writer/unknown | 165 | 0.9207 | 0.5652 | 0.1044 | 0.1000 | 0.0000 (0.0000, 0.0385) |

## Deep acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | 1.0000 | 0.9 | pass |
| pooled_ece | 0.0801 | 0.05 | fail |
| worst_stratum_ece | 0.8300 | 0.08 | fail |
| human_essay_high_fpr | 0.0000 | 0.02 | pass |
| esl_high_fpr | 0.0000 | 0.05 | pass |
| toefl_high_fpr | — | 0.05 | unmeasured |
| esl_native_gap | 0.0000 | 0.03 | pass |
| toefl_native_gap | — | 0.03 | unmeasured |

## Sampling

The fitted artifact has no recorded training selection.
Evaluation used seed 42 and a reservoir limit of 72 on the test cohort.
The Quick LM used 512 tokens per prefill during evaluation.

## Sentence and hardware evidence

Mixed-document F1 was 0.6316 across 1132 held-out sentences.
Metal/CUDA parity: unmeasured.
Release eligible: False.

- falcon_reference: unmeasured
- quantization: incomplete
- m6_load: passed

The length gate excluded 91 TOEFL essays. A cohort with no eligible essays has no estimated false-positive rate.

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.
