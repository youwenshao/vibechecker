import validation from "../../../eval/reports/phase-2/lenses.json";

export const lensVendors = {
  turnitin: "Turnitin",
  gptzero: "GPTZero",
  zerogpt: "ZeroGPT",
  grammarly: "Grammarly",
  veriguide: "VeriGuide",
} as const;
export type LensId = keyof typeof lensVendors;
export const lensIds = Object.keys(lensVendors) as LensId[];
export const lensEvidence = validation.lenses;
export const sentenceHighlights = validation.turnitin_highlights;
export const sentenceAudit = validation.sentence_validation;
