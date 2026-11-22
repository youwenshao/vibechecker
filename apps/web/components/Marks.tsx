"use client";
import { useId, useSyncExternalStore, type ReactNode } from "react";
import { glyphs, type Glyph } from "../lib/brand";

const r2 = (n: number) => Math.round(n * 100) / 100;
const TAU = Math.PI * 2;
export const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(" ");
const useSvgId = (prefix: string) => prefix + useId().replace(/[^\w-]/g, "");
const noop = () => () => {};
export const useHydrated = () => useSyncExternalStore(noop, () => true, () => false);

function InkFilter({ id, strength = 1, seed = 4, bias = 4.35 }: { id: string; strength?: number; seed?: number; bias?: number }) {
  return <filter id={id} x="-8%" y="-8%" width="116%" height="116%" colorInterpolationFilters="sRGB">
    <feTurbulence type="fractalNoise" baseFrequency={r2(0.9 / strength)} numOctaves={2} seed={seed} result="n" />
    <feColorMatrix in="n" type="matrix" values={`0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -7 ${bias}`} result="speck" />
    <feComposite in="SourceGraphic" in2="speck" operator="in" result="s" />
    <feTurbulence type="fractalNoise" baseFrequency={r2(0.045 / strength)} numOctaves={2} seed={seed + 5} result="w" />
    <feDisplacementMap in="s" in2="w" scale={r2(2.2 * strength)} xChannelSelector="R" yChannelSelector="G" />
  </filter>;
}

export const holoStops: [string, number][] = [["#e9fb98", 0], ["#c8bcf6", 0.32], ["#ffa8d6", 0.56], ["#a9b2ff", 0.8], ["#e9fb98", 1]];
function Holo({ id }: { id: string }) {
  return <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
    {holoStops.map(([color, offset]) => <stop key={offset} offset={offset} stopColor={color} />)}
  </linearGradient>;
}

/* Stamped: a rubber stamp whose tick overshoots its ring. */
const tick = "M12.5 24.8L20.6 33.2L40.6 7.6";
const tight = "1.5 4.2 43 43";
function Cut({ id, width = 10.5 }: { id: string; width?: number }) {
  return <mask id={id} maskUnits="userSpaceOnUse" x="-4" y="-4" width="56" height="56">
    <rect x="-4" y="-4" width="56" height="56" fill="#fff" />
    <path d={tick} fill="none" stroke="#000" strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" />
  </mask>;
}
function Rings({ mask, outer = 2.6, inner = 1 }: { mask: string; outer?: number; inner?: number }) {
  return <g mask={`url(#${mask})`}>
    <circle cx="23" cy="25.4" r="19.4" strokeWidth={outer} />
    <circle cx="23" cy="25.4" r="15.6" strokeWidth={inner} />
  </g>;
}

export function StampedMark() {
  const cut = useSvgId("cut");
  return <svg viewBox={tight} className="mk stamped" aria-hidden="true" focusable="false">
    <defs><Cut id={cut} /></defs>
    <g className="stamped-body"><g className="stamped-rings"><Rings mask={cut} /></g><path className="stamped-v" d={tick} /></g>
  </svg>;
}

export function StampedStamp({ seed = 3, fit }: { seed?: number; fit?: boolean }) {
  const ink = useSvgId("ink");
  const cut = useSvgId("cut");
  const body = (dx: number, dy: number, color: string, blend?: boolean) =>
    <g transform={`translate(${dx} ${dy})`} fill="none" style={{ stroke: color, mixBlendMode: blend ? "multiply" : undefined }}>
      <Rings mask={cut} outer={3.2} inner={1.4} />
      <path d={tick} strokeWidth={6.2} strokeLinecap="round" strokeLinejoin="round" />
    </g>;
  return <svg viewBox={fit ? tight : "0 0 48 48"} className="mk stamped-stamp" aria-hidden="true" focusable="false">
    <defs><InkFilter id={ink} strength={0.36} seed={seed + 4} bias={4.9} /><Cut id={cut} width={11} /></defs>
    <g filter={`url(#${ink})`}>{body(1.3, 1.1, "var(--royal-600)")}{body(0, 0, "var(--magenta-500)", true)}</g>
  </svg>;
}

export function StampedHolo({ fit }: { fit?: boolean }) {
  const holo = useSvgId("holo");
  return <svg viewBox={fit ? tight : "0 0 48 48"} className="mk stamped-holo" aria-hidden="true" focusable="false">
    <defs><Holo id={holo} /></defs>
    <circle cx="23" cy="25.4" r="20.6" fill={`url(#${holo})`} style={{ stroke: "var(--ink)" }} strokeWidth="1.4" />
    <circle cx="23" cy="25.4" r="16" fill="none" style={{ stroke: "var(--ink)" }} strokeOpacity=".45" strokeWidth=".8" />
    <path d={tick} fill="none" style={{ stroke: "var(--ink)" }} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

/* Tonight's seal: a foil disc with one glyph per night. */
export function Seal({ glyph }: { glyph: Glyph }) {
  const holo = useSvgId("holo");
  const { f, s } = glyphs[glyph];
  return <svg viewBox="1.7 4.1 42.6 42.6" className="mk stamped-seal" aria-hidden="true" focusable="false">
    <defs><Holo id={holo} /></defs>
    <circle cx="23" cy="25.4" r="20.6" fill={`url(#${holo})`} style={{ stroke: "var(--ink)" }} strokeWidth="1.4" />
    <circle cx="23" cy="25.4" r="16.4" fill="none" style={{ stroke: "var(--ink)" }} strokeOpacity=".45" strokeWidth=".8" />
    <g transform="translate(12.92 15.32) scale(.84)" style={{ fill: "var(--ink)", stroke: "var(--ink)" }} strokeLinecap="round" strokeLinejoin="round">
      {f && <path d={f} strokeWidth="1" />}
      {s && <path d={s} fill="none" strokeWidth="2.4" />}
    </g>
  </svg>;
}

/* The Look reports progress only. Its eyes never judge a result. */
const eyes = [17.25, 30.75];
export function Look({ happy }: { happy?: boolean }) {
  return <svg viewBox="3 12.5 42 23" className={cx("mk look", happy ? "st-happy" : "st-reading")} aria-hidden="true" focusable="false">
    <rect className="look-slot" x="3" y="12.5" width="42" height="23" rx="7.5" />
    <g className="look-eyes">{eyes.map((x) => <circle key={x} className="eye" cx={x} cy="24" r="4.3" />)}</g>
    <path className="look-happy" d="M13.9 26.4Q17.25 19.9 20.6 26.4M27.4 26.4Q30.75 19.9 34.1 26.4" />
  </svg>;
}

export function Roundel({ word, sub, date, seed = 4 }: { word: string; sub: string; date: string; seed?: number }) {
  const rim = useSvgId("rim");
  const ink = useSvgId("ink");
  return <svg viewBox="0 0 160 160" className="roundel" aria-hidden="true" focusable="false">
    <defs><path id={rim} d="M80 80m-63 0a63 63 0 1 1 126 0a63 63 0 1 1-126 0" /><InkFilter id={ink} seed={seed} /></defs>
    <g filter={`url(#${ink})`} style={{ fill: "var(--magenta-600)", stroke: "var(--magenta-600)" }}>
      <circle cx="80" cy="80" r="75" fill="none" strokeWidth="4.2" />
      <circle cx="80" cy="80" r="53.5" fill="none" strokeWidth="1.6" />
      <text className="t-display" fontSize="11.5" stroke="none">
        <textPath href={`#${rim}`} textLength={r2(TAU * 63 - 8)} lengthAdjust="spacing">{`VIBE CHECKED · ${date} · 氛圍檢查 · VIBECHECKER ·`}</textPath>
      </text>
      <path d="M45 62h70M45 109h70" strokeWidth="1.5" />
      <text x="80" y="92" textAnchor="middle" className="t-display" fontSize={[...word].length > 5 ? 26 : 31} letterSpacing="-.3" stroke="none">{word}</text>
      <text x="80" y="104" textAnchor="middle" className="t-mono" fontSize="9.5" letterSpacing="3.2" stroke="none">{sub}</text>
    </g>
  </svg>;
}

const outlines = {
  rect: <><rect x="6" y="14" width="148" height="82" rx="5" fill="none" strokeWidth="3.4" /><rect x="13" y="21" width="134" height="68" rx="2" fill="none" strokeWidth="1.2" /></>,
  circle: <><circle cx="80" cy="55" r="51" fill="none" strokeWidth="3.4" /><circle cx="80" cy="55" r="44" fill="none" strokeWidth="1.2" /></>,
  octagon: <><path d="M44 6h72l34 34v30l-34 34H44L10 70V40z" fill="none" strokeWidth="3.4" strokeLinejoin="round" /><path d="M47 13h66l29 29v26l-29 29H47L18 68V42z" fill="none" strokeWidth="1.2" strokeLinejoin="round" /></>,
  oval: <><ellipse cx="80" cy="55" rx="74" ry="46" fill="none" strokeWidth="3.4" /><ellipse cx="80" cy="55" rx="66" ry="39" fill="none" strokeWidth="1.2" /></>,
  hex: <><path d="M38 8h84l30 47-30 47H38L8 55z" fill="none" strokeWidth="3.4" strokeLinejoin="round" /><path d="M42 15h76l25 40-25 40H42L17 55z" fill="none" strokeWidth="1.2" strokeLinejoin="round" /></>,
};
const room = { rect: 126, circle: 76, octagon: 112, oval: 108, hex: 100 };
export type LensShape = keyof typeof outlines;
// Approximate advance widths in ems keep long readings inside each outline.
const ems = (text: string) => [...text].reduce((width, ch) => width + (/[\u2e80-\u9fff\uff00-\uffef]/.test(ch) ? 1 : 0.64), 0);

export function LensStamp({ shape, vendor, value, color, seed = 3 }: { shape: LensShape; vendor: string; value: string; color: string; seed?: number }) {
  const ink = useSvgId("ink");
  const size = r2(Math.min(value.length > 4 ? 22 : 30, room[shape] / ems(value)));
  const label = r2(Math.min(shape === "circle" ? 7.4 : 8.6, (room[shape] + 8) / (ems(vendor) + vendor.length * 0.2)));
  return <svg viewBox="0 0 160 110" className="lens-stamp" aria-hidden="true" focusable="false">
    <defs><InkFilter id={ink} strength={0.9} seed={seed} /></defs>
    <g filter={`url(#${ink})`} style={{ fill: color, stroke: color }}>
      {outlines[shape]}
      <text x="80" y={shape === "circle" ? 46 : 44} textAnchor="middle" className="t-mono" fontSize={label} letterSpacing={r2(label * 0.18)} stroke="none">{vendor.toUpperCase()}</text>
      <text x="80" y={r2(62 + size / 2.6)} textAnchor="middle" className="t-display" fontSize={size} letterSpacing="-.3" stroke="none">{value.toUpperCase()}</text>
    </g>
  </svg>;
}

export function Chop() {
  const ink = useSvgId("ink");
  return <svg viewBox="0 0 64 64" className="chop" aria-hidden="true" focusable="false">
    <defs><InkFilter id={ink} strength={0.7} seed={11} /></defs>
    <g filter={`url(#${ink})`}>
      <rect x="3" y="3" width="58" height="58" rx="5" style={{ fill: "var(--magenta-600)" }} />
      <rect x="7.5" y="7.5" width="49" height="49" rx="2" fill="none" style={{ stroke: "var(--paper)" }} strokeWidth="1.6" />
      <g className="t-hk" fontSize="20" style={{ fill: "var(--paper)" }} textAnchor="middle">
        <text x="43.5" y="30">氛</text><text x="43.5" y="51">圍</text><text x="20.5" y="30">檢</text><text x="20.5" y="51">查</text>
      </g>
    </g>
  </svg>;
}

export function SentencePrint({ heats }: { heats: number[] }) {
  const row = (140 - 26) / Math.max(heats.length, 1);
  return <svg viewBox="0 0 100 140" preserveAspectRatio="none" aria-hidden="true" focusable="false">
    {heats.map((v, i) => <rect key={i} x="10" y={r2(12 + i * row)} width={r2(14 + v * 72)} height={r2(row * 0.62)} rx={r2(row * 0.31)}
      style={{ fill: "var(--royal-600)" }} fillOpacity={r2(0.3 + v * 0.62)} />)}
  </svg>;
}

let engraving: [string, string] | undefined;
function engrave(): [string, string] {
  if (engraving) return engraving;
  const [w, h] = [560, 353];
  let waves = "";
  for (let k = 0; k < 26; k++) {
    const y0 = (k + 0.5) * (h / 26);
    for (let x = 0; x <= w; x += 5) {
      const y = y0 + 3.2 * Math.sin((x / 58) * TAU + k * 0.36) + 1.2 * Math.sin((x / 23.8) * TAU - k * 0.58);
      waves += `${x ? "L" : "M"}${x} ${r2(y)}`;
    }
  }
  let rosette = "";
  const [R, r, d, k] = [92, 33, 46, 59 / 33];
  for (let i = 0; i <= 2400; i++) {
    const t = (i / 2400) * TAU * 11;
    rosette += `${i ? "L" : "M"}${r2(w * 0.66 + (R - r) * Math.cos(t) + d * Math.cos(k * t))} ${r2(h * 0.58 + (R - r) * Math.sin(t) - d * Math.sin(k * t))}`;
  }
  return (engraving = [waves, rosette]);
}

// The engraving runs to tens of kilobytes, so it is drawn after hydration instead of shipping in HTML.
export function Guilloche() {
  const hydrated = useHydrated();
  if (!hydrated) return null;
  const [waves, rosette] = engrave();
  return <svg className="pass-guilloche" viewBox="0 0 560 353" preserveAspectRatio="none" aria-hidden="true" focusable="false">
    <path d={waves} fill="none" style={{ stroke: "var(--royal-600)" }} strokeOpacity=".11" strokeWidth=".6" />
    <path d={rosette} fill="none" style={{ stroke: "var(--royal-600)" }} strokeOpacity=".13" strokeWidth=".5" />
  </svg>;
}

export function Band({ children, total, used, className }: { children: ReactNode; total: number; used: number; className?: string }) {
  return <div className={cx("band", className)}>
    <svg className="band-end" viewBox="0 0 18 48" preserveAspectRatio="none" aria-hidden="true" focusable="false">
      <path d="M18 .6H7.5L2 6.6l5.5 6-5.5 6 5.5 6-5.5 6 5.5 6-5.5 6 5.5 5.8H18" />
    </svg>
    <span>{children}</span>
    {total > 0 && total <= 12 && <span className="stubs" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => <i key={i} className={i >= total - used ? "used" : undefined} />)}
    </span>}
    <span className="band-rivet" aria-hidden="true" />
  </div>;
}

type RisoTag = "p" | "span" | "h1" | "h2" | "h3";
export function Riso({ as: Tag = "span", className, children, ghost, testId, label }: {
  as?: RisoTag; className?: string; children: ReactNode; ghost?: ReactNode; testId?: string; label?: string;
}) {
  return <Tag className={cx("riso", className)} aria-label={label}>
    <span className="riso-a" data-testid={testId}>{children}</span>
    <span className="riso-b" aria-hidden="true">{ghost ?? children}</span>
  </Tag>;
}
