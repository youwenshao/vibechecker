import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import en from "../messages/en.json";
import zh from "../messages/zh-HK.json";
import { wordCount } from "./essay";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
function luminance(hex: string) {
  const components = hex.slice(1).match(/../g)!.map((pair) => parseInt(pair, 16) / 255)
    .map((s) => s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4);
  return components[0] * .2126 + components[1] * .7152 + components[2] * .0722;
}
function contrast(a: string, b: string) {
  const [lo, hi] = [luminance(a), luminance(b)].sort((x, y) => x - y);
  return (hi + .05) / (lo + .05);
}
function keys(value: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(value).flatMap(([key, v]) => typeof v === "object" && v
    ? keys(v as Record<string, unknown>, prefix + key + ".") : [prefix + key]).sort();
}
describe("UI checks", () => {
  it("has complete English and Hong Kong Chinese catalogues", () => expect(keys(en)).toEqual(keys(zh)));
  it("counts Unicode words, internal apostrophes and hyphens", () => {
    expect(wordCount("cafe\u0301 — 2026, student’s, shelf-life. 😀")).toBe(4);
    expect(wordCount("　")).toBe(0);
  });
  it("meets AA contrast for foreground/background pairs used by the theme", () => {
    const token = (name: string) => css.match(new RegExp("--color-" + name + ": (#[a-f0-9]{6})"))![1];
    for (const background of ["paper", "panel", "accent", "heat-1", "heat-2", "heat-3"]) {
      expect(contrast(token("ink"), token(background))).toBeGreaterThanOrEqual(4.5);
    }
    const muted = css.match(/--muted: (#[a-f0-9]{6})/)![1];
    for (const background of ["paper", "panel"]) expect(contrast(muted, token(background))).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#55534a", "#e4e2da")).toBeGreaterThanOrEqual(4.5);
  });
});
