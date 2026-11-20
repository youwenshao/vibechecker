# roberta-large-liang-v1

Locally measured RoBERTa-large GPT-2 output detector, first 510 tokens per document. All available essay lengths are included for the baseline. Mixed and high thresholds are 0.50 and 0.90. Short essays in this offline comparison receive a length refusal in the Quick service. Hewlett is the US comparison cohort. Individual native-language status is unverified.

Backend `torch-mps`. Scored 279 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 279 | 0.7125 | 0.0000 | 0.1146 | 0.1247 | 0.0282 (0.0137, 0.0571) |
| attack/none | 279 | 0.7125 | 0.0000 | 0.1146 | 0.1247 | 0.0282 (0.0137, 0.0571) |
| dataset/liang/college-ai | 31 | — | — | 0.7450 | 0.6636 | — |
| dataset/liang/college-human | 70 | — | — | 0.0092 | 0.0011 | 0.0000 (0.0000, 0.0520) |
| dataset/liang/hewlett | 88 | — | — | 0.0619 | 0.0287 | 0.0000 (0.0000, 0.0418) |
| dataset/liang/toefl | 90 | — | — | 0.1816 | 0.1293 | 0.0778 (0.0382, 0.1519) |
| fairness/ESL-essay | 90 | — | — | 0.1816 | 0.1293 | 0.0778 (0.0382, 0.1519) |
| generator/gpt-3 | 31 | — | — | 0.7450 | 0.6636 | — |
| generator/human | 248 | — | — | 0.0905 | 0.0574 | 0.0282 (0.0137, 0.0571) |
| genre/essay | 279 | 0.7125 | 0.0000 | 0.1146 | 0.1247 | 0.0282 (0.0137, 0.0571) |
| length/150-299 | 42 | 0.7909 | 0.1000 | 0.3630 | 0.3321 | 0.0000 (0.0000, 0.1487) |
| length/300-599 | 96 | 0.6349 | 0.2000 | 0.1092 | 0.0950 | 0.0000 (0.0000, 0.0428) |
| length/600-1199 | 49 | — | — | 0.0112 | 0.0015 | 0.0000 (0.0000, 0.0727) |
| length/<150 | 92 | 0.8901 | 0.0000 | 0.1760 | 0.1267 | 0.0769 (0.0378, 0.1504) |
| split/test | 279 | 0.7125 | 0.0000 | 0.1146 | 0.1247 | 0.0282 (0.0137, 0.0571) |
| writer/ESL | 90 | — | — | 0.1816 | 0.1293 | 0.0778 (0.0382, 0.1519) |
| writer/native_proxy | 88 | — | — | 0.0619 | 0.0287 | 0.0000 (0.0000, 0.0418) |
| writer/unknown | 101 | 0.8553 | 0.3548 | 0.2223 | 0.2044 | 0.0000 (0.0000, 0.0520) |

## Quick acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | 0.7125 | 0.85 | fail |
| pooled_ece | 0.1146 | 0.05 | fail |
| worst_stratum_ece | 0.7450 | 0.08 | fail |
| human_essay_high_fpr | 0.0282 | 0.02 | fail |
| esl_high_fpr | 0.0778 | 0.05 | fail |
| toefl_high_fpr | 0.0778 | 0.05 | fail |
| esl_native_gap | 0.0778 | 0.03 | fail |
| toefl_native_gap | 0.0778 | 0.03 | fail |

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.
