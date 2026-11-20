# RFC 004 · Quick calibration and uncertainty

Phase 0 uses a document-level gradient-boosted stacker and held-out isotonic calibration with a balanced class prior. The index describes similarity to writing in the reference data. It cannot identify the author or establish misconduct.

The pooled curve applies until a length stratum has at least 1,000 calibration examples from both classes combined, with each class represented. The 5th and 95th percentiles of 200 stratified bootstrap calibrators bound the interval. Minimum widths in ascending word-count bins are 20, 14, 10 and 8 index points. Ties in the human calibration scores are kept together when selecting the mixed and high thresholds.

## Private demo and release gates

Quick essay AUROC must reach 0.85. Pooled ECE must be at most 0.05 and every stratum at most 0.08. The human-essay high-band false-positive rate must be at most 2%. ESL and TOEFL rates must each be at most 5%, within three percentage points of the comparison cohort. Publish Wilson intervals. For comparisons with a prior release, use the same cohort and allow a maximum regression of 0.01. Require Metal/CUDA agreement within one index point across at least 200 fixtures. The sentence-level agreement gate applies when the sentence head ships.

The private demo's first fp32 run included 436 held-out documents. Worst-stratum ECE was 0.2677. All 91 TOEFL passages triggered the length gate. The report records the missing TOEFL estimate, preserves the gates, and marks the model ineligible for release. [Full scorecard](../../eval/reports/quick-m6-fp32-v0/report.md)
