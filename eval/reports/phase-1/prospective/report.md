# deep-qwen7b-q4-p512-v4

Deep runtime scored eligible held-out English documents. Hewlett is the US comparison cohort. TOEFL estimates cover eligible essays only.

Backend `mlx-metal`. Scored 435 held-out documents.

## Results

| Stratum | Documents | AUROC | TPR at 1% FPR | ECE | Brier | High FPR (95% Wilson interval) |
|---|---:|---:|---:|---:|---:|---|
| pooled | 435 | 0.9998 | 0.9944 | 0.0087 | 0.0048 | 0.0117 (0.0040, 0.0338) |
| attack/alternative_spelling | 13 | — | — | 0.0000 | 0.0000 | — |
| attack/article_deletion | 14 | — | — | 0.0000 | 0.0000 | — |
| attack/homoglyph | 3 | — | — | 0.0000 | 0.0000 | — |
| attack/insert_paragraphs | 4 | — | — | 0.0000 | 0.0000 | — |
| attack/none | 349 | 0.9997 | 0.9891 | 0.0090 | 0.0058 | 0.0117 (0.0040, 0.0338) |
| attack/number | 11 | — | — | 0.0000 | 0.0000 | — |
| attack/paraphrase | 15 | — | — | 0.0420 | 0.0043 | — |
| attack/perplexity_misspelling | 11 | — | — | 0.0036 | 0.0001 | — |
| attack/synonym | 15 | — | — | 0.0000 | 0.0000 | — |
| dataset/asap | 115 | — | — | 0.0067 | 0.0029 | 0.0087 (0.0015, 0.0476) |
| dataset/ellipse | 116 | — | — | 0.0121 | 0.0062 | 0.0172 (0.0047, 0.0607) |
| dataset/raid | 118 | 1.0000 | 1.0000 | 0.0122 | 0.0083 | 0.0000 (0.0000, 0.1287) |
| dataset/raid-attacks | 86 | — | — | 0.0078 | 0.0008 | — |
| fairness/ESL-essay | 122 | — | — | 0.0115 | 0.0059 | 0.0164 (0.0045, 0.0578) |
| generator/chatgpt | 9 | — | — | 0.0000 | 0.0000 | — |
| generator/cohere | 8 | — | — | 0.1250 | 0.1154 | — |
| generator/cohere-chat | 9 | — | — | 0.0356 | 0.0057 | — |
| generator/gpt2 | 30 | — | — | 0.0093 | 0.0010 | — |
| generator/gpt3 | 7 | — | — | 0.0057 | 0.0002 | — |
| generator/gpt4 | 9 | — | — | 0.0000 | 0.0000 | — |
| generator/human | 257 | — | — | 0.0084 | 0.0041 | 0.0117 (0.0040, 0.0338) |
| generator/llama-chat | 29 | — | — | 0.0090 | 0.0011 | — |
| generator/mistral | 28 | — | — | 0.0043 | 0.0002 | — |
| generator/mistral-chat | 7 | — | — | 0.0000 | 0.0000 | — |
| generator/mpt | 28 | — | — | 0.0032 | 0.0001 | — |
| generator/mpt-chat | 14 | — | — | 0.0000 | 0.0000 | — |
| genre/essay | 231 | — | — | 0.0094 | 0.0045 | 0.0130 (0.0044, 0.0375) |
| genre/other | 204 | 1.0000 | 1.0000 | 0.0103 | 0.0051 | 0.0000 (0.0000, 0.1287) |
| length/1200+ | 10 | — | — | 0.0000 | 0.0000 | 0.0000 (0.0000, 0.2775) |
| length/300-599 | 318 | 0.9998 | 0.9944 | 0.0105 | 0.0055 | 0.0143 (0.0039, 0.0506) |
| length/600-1199 | 107 | — | — | 0.0066 | 0.0033 | 0.0093 (0.0017, 0.0510) |
| split/test | 435 | 0.9998 | 0.9944 | 0.0087 | 0.0048 | 0.0117 (0.0040, 0.0338) |
| writer/ESL | 122 | — | — | 0.0115 | 0.0059 | 0.0164 (0.0045, 0.0578) |
| writer/unknown | 313 | 0.9999 | 0.9944 | 0.0079 | 0.0044 | 0.0074 (0.0013, 0.0408) |

## Deep acceptance gates

| Measure | Observed | Gate | Status |
|---|---:|---:|---|
| essay_auroc | — | 0.9 | unmeasured |
| pooled_ece | 0.0087 | 0.05 | pass |
| worst_stratum_ece | 0.1250 | 0.08 | fail |
| human_essay_high_fpr | 0.0130 | 0.02 | pass |
| esl_high_fpr | 0.0164 | 0.05 | pass |
| toefl_high_fpr | — | 0.05 | unmeasured |
| esl_native_gap | — | 0.03 | unmeasured |
| toefl_native_gap | — | 0.03 | unmeasured |

## Sampling

The refitted stacker used seed 42, a training limit of 160 and a calibration limit of 352 per source and class. Dataset order was raid, raid-attacks, asap, ellipse, liang.
The prospective audit reserved 512 documents before language screening. Plan SHA-256 was `98e100bdc12a14cefbe35c88f6b48397577e4f11388978c007dbdea6aabaf170`.
The Quick LM used 512 tokens per prefill during evaluation.

## Sentence and hardware evidence

Mixed-document F1 was 0.6689 across 2895 held-out sentences.
Metal/CUDA parity: unmeasured.
Release eligible: False.

- falcon_reference: unmeasured
- quantization: incomplete
- m6_load: passed

The JSON report includes the input SHA-256 manifest, selection settings, refusal counts and timing.
