export const glyphNames = ["headphones", "heart", "bolt", "disco", "moon", "sparkles", "note", "cherry"] as const;
export type Glyph = (typeof glyphNames)[number];

// Paths sit in a 24-unit box; f is filled and s is stroked.
export const glyphs: Record<Glyph, { f?: string; s?: string }> = {
  headphones: {
    s: "M4.6 15V12a7.4 7.4 0 0 1 14.8 0V15",
    f: "M2.6 14.8a2 2 0 0 1 2-2H7.4v8.6H4.6a2 2 0 0 1-2-2ZM21.4 14.8a2 2 0 0 0-2-2H16.6v8.6h2.8a2 2 0 0 0 2-2Z",
  },
  heart: { f: "M12 20.6C11 19.9 3 14.9 3 8.9C3 6 5.2 3.8 7.9 3.8C9.7 3.8 11.2 4.8 12 6.3C12.8 4.8 14.3 3.8 16.1 3.8C18.8 3.8 21 6 21 8.9C21 14.9 13 19.9 12 20.6Z" },
  bolt: { f: "M13.6 2L4.8 13.6H11.2L10 22L19.2 10H12.8Z" },
  disco: {
    s: "M12 1.6V5.2M3.8 13.4A8.2 8.2 0 1 0 20.2 13.4A8.2 8.2 0 1 0 3.8 13.4ZM4.4 10.4H19.6M4.4 16.4H19.6M12 5.2A3.4 8.2 0 0 0 12 21.6A3.4 8.2 0 0 0 12 5.2",
    f: "M19.4 1.4C19.6 2.9 20.2 3.5 21.7 3.7C20.2 3.9 19.6 4.5 19.4 6C19.2 4.5 18.6 3.9 17.1 3.7C18.6 3.5 19.2 2.9 19.4 1.4Z",
  },
  moon: { f: "M16 4.7A9 9 0 1 0 20 15.6A7 7 0 0 1 16 4.7Z" },
  sparkles: {
    f: "M10.5 3C11.3 8.7 13.8 11.2 19.5 12C13.8 12.8 11.3 15.3 10.5 21C9.7 15.3 7.2 12.8 1.5 12C7.2 11.2 9.7 8.7 10.5 3ZM18.5 2.5C18.8 4.4 19.6 5.2 21.5 5.5C19.6 5.8 18.8 6.6 18.5 8.5C18.2 6.6 17.4 5.8 15.5 5.5C17.4 5.2 18.2 4.4 18.5 2.5Z",
  },
  note: { f: "M4.6 17.6a4 3.1 0 1 0 8 0a4 3.1 0 1 0 -8 0Z", s: "M12.1 17.4V3.2M12.1 3.2C12.6 6.9 18.4 7.6 17.4 13.4" },
  cherry: {
    f: "M2.8 17.2a4.2 4.2 0 1 0 8.4 0a4.2 4.2 0 1 0 -8.4 0ZM12.8 18.2a4.2 4.2 0 1 0 8.4 0a4.2 4.2 0 1 0 -8.4 0ZM15.6 3.6C17.6 1.9 20.6 2 22 3.4C20.2 5.2 17.4 5.2 15.6 3.6Z",
    s: "M7 13C8.2 8.6 11.4 5.2 15.6 3.6M17 14C16.2 10 15.6 6.6 15.6 3.6",
  },
};

const hongKong = 8 * 3_600_000;
const day = 86_400_000;
const zone = "Asia/Hong_Kong";

// Tonight's seal follows the Hong Kong calendar day of the check and never its score.
export function tonightGlyph(at: number): Glyph {
  return glyphNames[((Math.floor((at + hongKong) / day) % 8) + 8) % 8];
}

export function sentenceHeats(sentences?: readonly { score: number }[], slots = 22): number[] {
  if (!sentences?.length) return [];
  if (sentences.length <= slots) return sentences.map((item) => item.score);
  return Array.from({ length: slots }, (_, i) => {
    const part = sentences.slice(Math.floor((i * sentences.length) / slots), Math.floor(((i + 1) * sentences.length) / slots));
    return Math.max(...part.map((item) => item.score));
  });
}

const parts = (at: number) => {
  const date = new Date(at + hongKong);
  return [date.getUTCDate(), date.getUTCMonth() + 1, date.getUTCFullYear() % 100].map((n) => String(n).padStart(2, "0"));
};
export const flyerDate = (at: number) => parts(at).join(".");
export const stampDate = (at: number) =>
  new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: zone }).format(at).toUpperCase();
export const passDate = (at: number, locale: string) =>
  new Intl.DateTimeFormat(locale === "en" ? "en-GB" : locale, { day: "numeric", month: "short", year: "numeric", timeZone: zone }).format(at);

type Reading = { index: number; interval: { low: number; high: number }; band: string; wordCount: number };
const three = (n: number) => String(n).padStart(3, "0");
export function machineLines(result: Reading, at: number, id = ""): [string, string] {
  const [dd, mm, yy] = parts(at);
  const serial = id.replaceAll("-", "").slice(0, 5).toUpperCase() || "VIBES";
  return [
    `VC<DEEP<<${three(result.index)}<${three(result.interval.low)}<${three(result.interval.high)}<<${result.band.toUpperCase()}`,
    `${yy}${mm}${dd}<${result.wordCount}W<${serial}<<NOT<PROOF`,
  ];
}
