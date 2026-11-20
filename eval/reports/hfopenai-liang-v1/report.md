# hfopenai-liang-v1

Replay of Liang et al.’s archived HFOpenAI scores. All available essay lengths are included for the baseline. Mixed and high thresholds are 0.50 and 0.90. Short essays in this offline comparison receive a length refusal in the Quick service. Hewlett is the US comparison cohort. Individual native-language status is unverified.

Backend `archived-hfopenai`. Scored 279 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 279 | 0.7859 | 0.1935 | 0.2469 | 0.2168 | 0.1290 (0.0929, 0.1765) |
| attack/none | 279 | 0.7859 | 0.1935 | 0.2469 | 0.2168 | 0.1290 (0.0929, 0.1765) |
| dataset/liang/college-ai | 31 | — | — | 0.4093 | 0.3853 | — |
| dataset/liang/college-human | 70 | — | — | 0.0092 | 0.0014 | 0.0000 (0.0000, 0.0520) |
| dataset/liang/hewlett | 88 | — | — | 0.0987 | 0.0744 | 0.0341 (0.0117, 0.0955) |
| dataset/liang/toefl | 90 | — | — | 0.5629 | 0.4654 | 0.3222 (0.2347, 0.4243) |
| fairness/ESL-essay | 90 | — | — | 0.5629 | 0.4654 | 0.3222 (0.2347, 0.4243) |
| generator/gpt-3 | 31 | — | — | 0.4093 | 0.3853 | — |
| generator/human | 248 | — | — | 0.2419 | 0.1957 | 0.1290 (0.0929, 0.1765) |
| genre/essay | 279 | 0.7859 | 0.1935 | 0.2469 | 0.2168 | 0.1290 (0.0929, 0.1765) |
| length/150-299 | 42 | 0.8841 | 0.4500 | 0.2149 | 0.2178 | 0.0455 (0.0081, 0.2180) |
| length/300-599 | 96 | 0.8884 | 0.2000 | 0.1090 | 0.0962 | 0.0233 (0.0064, 0.0809) |
| length/600-1199 | 49 | — | — | 0.0161 | 0.0043 | 0.0000 (0.0000, 0.0727) |
| length/<150 | 92 | 0.9341 | 0.0000 | 0.5506 | 0.4553 | 0.3187 (0.2320, 0.4201) |
| split/test | 279 | 0.7859 | 0.1935 | 0.2469 | 0.2168 | 0.1290 (0.0929, 0.1765) |
| writer/ESL | 90 | — | — | 0.5629 | 0.4654 | 0.3222 (0.2347, 0.4243) |
| writer/native_proxy | 88 | — | — | 0.0987 | 0.0744 | 0.0341 (0.0117, 0.0955) |
| writer/unknown | 101 | 0.9465 | 0.6129 | 0.1296 | 0.1192 | 0.0000 (0.0000, 0.0520) |

## Quick acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | 0.7859 | 0.85 | fail |
| pooled_ece | 0.2469 | 0.05 | fail |
| worst_stratum_ece | 0.5629 | 0.08 | fail |
| human_essay_high_fpr | 0.1290 | 0.02 | fail |
| esl_high_fpr | 0.3222 | 0.05 | fail |
| toefl_high_fpr | 0.3222 | 0.05 | fail |
| esl_native_gap | 0.2881 | 0.03 | fail |
| toefl_native_gap | 0.2881 | 0.03 | fail |

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.
