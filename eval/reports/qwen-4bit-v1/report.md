# qwen-4bit-v1

Deep runtime scored eligible held-out English documents. Hewlett is the US comparison cohort. TOEFL estimates cover eligible essays only.

Backend `mlx-metal`. Scored 54 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 54 | 0.8858 | 0.5556 | 0.1074 | 0.1160 | 0.0000 (0.0000, 0.0964) |
| attack/none | 50 | 0.8601 | 0.5000 | 0.1264 | 0.1198 | 0.0000 (0.0000, 0.0964) |
| attack/paraphrase | 1 | — | — | 0.5200 | 0.2704 | — |
| attack/perplexity_misspelling | 2 | — | — | 0.0000 | 0.0000 | — |
| attack/synonym | 1 | — | — | 0.0000 | 0.0000 | — |
| dataset/asap | 6 | — | — | 0.1017 | 0.0620 | 0.0000 (0.0000, 0.3903) |
| dataset/ellipse | 8 | — | — | 0.0663 | 0.0186 | 0.0000 (0.0000, 0.3244) |
| dataset/liang/college-ai | 5 | — | — | 0.3000 | 0.2174 | — |
| dataset/liang/college-human | 9 | — | — | 0.1600 | 0.0768 | 0.0000 (0.0000, 0.2991) |
| dataset/liang/hewlett | 8 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.3244) |
| dataset/raid | 14 | 0.7333 | 0.5556 | 0.2900 | 0.2638 | 0.0000 (0.0000, 0.4345) |
| dataset/raid-attacks | 4 | — | — | 0.1300 | 0.0676 | — |
| fairness/ESL-essay | 9 | — | — | 0.0589 | 0.0165 | 0.0000 (0.0000, 0.2991) |
| generator/cohere | 1 | — | — | 0.5200 | 0.2704 | — |
| generator/gpt-3 | 5 | — | — | 0.3000 | 0.2174 | — |
| generator/gpt2 | 3 | — | — | 0.3333 | 0.3333 | — |
| generator/gpt4 | 1 | — | — | 0.0800 | 0.0064 | — |
| generator/human | 36 | — | — | 0.1039 | 0.0476 | 0.0000 (0.0000, 0.0964) |
| generator/llama-chat | 2 | — | — | 0.3000 | 0.1384 | — |
| generator/mistral | 3 | — | — | 0.4633 | 0.3840 | — |
| generator/mpt | 3 | — | — | 0.2900 | 0.2523 | — |
| genre/essay | 36 | 0.9452 | 0.6000 | 0.0844 | 0.0639 | 0.0000 (0.0000, 0.1103) |
| genre/other | 18 | 0.8000 | 0.6154 | 0.2056 | 0.2202 | 0.0000 (0.0000, 0.4345) |
| length/300-599 | 46 | 0.8929 | 0.5556 | 0.1033 | 0.1238 | 0.0000 (0.0000, 0.1206) |
| length/600-1199 | 8 | — | — | 0.1613 | 0.0712 | 0.0000 (0.0000, 0.3244) |
| split/test | 54 | 0.8858 | 0.5556 | 0.1074 | 0.1160 | 0.0000 (0.0000, 0.0964) |
| writer/ESL | 9 | — | — | 0.0589 | 0.0165 | 0.0000 (0.0000, 0.2991) |
| writer/native_proxy | 8 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.3244) |
| writer/unknown | 37 | 0.8509 | 0.5556 | 0.1424 | 0.1652 | 0.0000 (0.0000, 0.1682) |

## Deep acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | 0.9452 | 0.9 | pass |
| pooled_ece | 0.1074 | 0.05 | fail |
| worst_stratum_ece | 0.5200 | 0.08 | fail |
| human_essay_high_fpr | 0.0000 | 0.02 | pass |
| esl_high_fpr | 0.0000 | 0.05 | pass |
| toefl_high_fpr | — | 0.05 | unmeasured |
| esl_native_gap | 0.0000 | 0.03 | pass |
| toefl_native_gap | — | 0.03 | unmeasured |

## Sentence and hardware evidence

Mixed-document F1 was 0.7312 across 297 held-out sentences.
Metal/CUDA parity: unmeasured.
Release eligible: False.

- falcon_reference: unmeasured
- quantization: unmeasured
- m6_load: unmeasured

The length gate excluded 91 TOEFL essays. A cohort with no eligible essays has no estimated false-positive rate.

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.
