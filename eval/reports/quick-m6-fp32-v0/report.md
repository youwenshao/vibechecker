# quick-m6-fp32-v0

Real Quick pipeline. RAID and MAGE overlap the encoder's published training domains. Hewlett is the study's US comparison cohort. Individual native-language status is unverified.

Backend `mlx-metal`. Scored 436 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 436 | 0.9902 | 0.9583 | 0.0156 | 0.0142 | 0.0000 (0.0000, 0.0120) |
| attack/none | 436 | 0.9902 | 0.9583 | 0.0156 | 0.0142 | 0.0000 (0.0000, 0.0120) |
| dataset/ellipse | 86 | — | — | 0.0349 | 0.0137 | 0.0000 (0.0000, 0.0428) |
| dataset/liang/college-ai | 30 | — | — | 0.0000 | 0.0000 | — |
| dataset/liang/college-human | 65 | — | — | 0.0140 | 0.0079 | 0.0000 (0.0000, 0.0558) |
| dataset/liang/hewlett | 74 | — | — | 0.0031 | 0.0007 | 0.0000 (0.0000, 0.0493) |
| dataset/raid | 181 | 0.9861 | 0.9444 | 0.0182 | 0.0245 | 0.0000 (0.0000, 0.0405) |
| fairness/ESL-essay | 86 | — | — | 0.0349 | 0.0137 | 0.0000 (0.0000, 0.0428) |
| generator/chatgpt | 3 | — | — | 0.0000 | 0.0000 | — |
| generator/cohere | 3 | — | — | 0.1067 | 0.0341 | — |
| generator/cohere-chat | 2 | — | — | 0.0000 | 0.0000 | — |
| generator/gpt-3 | 30 | — | — | 0.0000 | 0.0000 | — |
| generator/gpt2 | 15 | — | — | 0.0180 | 0.0016 | — |
| generator/gpt3 | 4 | — | — | 0.0000 | 0.0000 | — |
| generator/gpt4 | 2 | — | — | 0.0000 | 0.0000 | — |
| generator/human | 316 | — | — | 0.0213 | 0.0078 | 0.0000 (0.0000, 0.0120) |
| generator/llama-chat | 15 | — | — | 0.0060 | 0.0005 | — |
| generator/mistral | 13 | — | — | 0.2677 | 0.2296 | — |
| generator/mistral-chat | 16 | — | — | 0.0000 | 0.0000 | — |
| generator/mpt | 12 | — | — | 0.0717 | 0.0501 | — |
| generator/mpt-chat | 5 | — | — | 0.0000 | 0.0000 | — |
| genre/essay | 255 | 1.0000 | 1.0000 | 0.0162 | 0.0068 | 0.0000 (0.0000, 0.0168) |
| genre/other | 181 | 0.9861 | 0.9444 | 0.0182 | 0.0245 | 0.0000 (0.0000, 0.0405) |
| length/1200+ | 1 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.7935) |
| length/150-299 | 170 | 0.9910 | 0.9701 | 0.0165 | 0.0134 | 0.0000 (0.0000, 0.0360) |
| length/300-599 | 202 | 0.9889 | 0.9434 | 0.0150 | 0.0144 | 0.0000 (0.0000, 0.0251) |
| length/600-1199 | 63 | — | — | 0.0252 | 0.0155 | 0.0000 (0.0000, 0.0575) |
| split/test | 436 | 0.9902 | 0.9583 | 0.0156 | 0.0142 | 0.0000 (0.0000, 0.0120) |
| writer/ESL | 86 | — | — | 0.0349 | 0.0137 | 0.0000 (0.0000, 0.0428) |
| writer/native_proxy | 74 | — | — | 0.0031 | 0.0007 | 0.0000 (0.0000, 0.0493) |
| writer/unknown | 276 | 0.9901 | 0.9583 | 0.0129 | 0.0179 | 0.0000 (0.0000, 0.0240) |

## Quick acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | 1.0000 | 0.85 | pass |
| pooled_ece | 0.0156 | 0.05 | pass |
| worst_stratum_ece | 0.2677 | 0.08 | fail |
| human_essay_high_fpr | 0.0000 | 0.02 | pass |
| esl_high_fpr | 0.0000 | 0.05 | pass |
| toefl_high_fpr | — | 0.05 | unmeasured |
| esl_native_gap | 0.0000 | 0.03 | pass |
| toefl_native_gap | — | 0.03 | unmeasured |

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.
