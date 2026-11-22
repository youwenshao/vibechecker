# RFC-005 · Detector lenses

Each lens interprets signals from the frozen detector on our own hardware. A lens cannot change the index, interval, band or flags. The result records the parameter version. Earlier results can be opened without lens values.

The Turnitin-style lens counts words in sentences above its cutoff and masks shares from 1% to 19%. Quick omits the sentence estimate because it has no sentence head. The other lenses combine document features with nonnegative weights. GPTZero-style uses an ESL essay calibration set. ZeroGPT-style uses a published independent benchmark. Grammarly-style and VeriGuide-style use human reference bands because their sources provide no numerical operating point.

The fitter checks the input digests and separates calibration and validation. Its two-percentage-point tolerance applies to published numerical targets. The methodology gives the denominator, source and any missed tolerance. Each lens links to the evidence and identifies the proprietary vendor and the limits of the approximation. [Parameters](../../engine/lenses/v1.yaml) · [Measurements](../plans/phase-2-evidence.md)
