import { useEffect, useState } from "react";
import { animate, motion, useReducedMotion } from "motion/react";
import { useLocale, useTranslations } from "next-intl";
import type { Verdict } from "../lib/check-stream";

const paths = {
  arrow: "M4 12h15m-6-6 6 6-6 6",
  attach: "m8 15 7.4-7.4a2.4 2.4 0 0 1 3.4 3.4L9.2 20.6a5 5 0 0 1-7.1-7.1l10-10",
  lock: "M7 10V7a5 5 0 0 1 10 0v3M5 10h14v11H5zM12 14v3",
  bolt: "m13 2-9 12h7l-1 8 10-13h-8z",
  close: "m5 5 14 14M19 5 5 19",
  erase: "M3 6h18M8 6V3h8v3M6 6l1 15h10l1-15M10 10v7m4-7v7",
  pencil: "m4 16 11-11 4 4L8 20l-5 1zM13 7l4 4",
  globe: "M2 12h20M12 2c-6 6-6 14 0 20 6-6 6-14 0-20z",
} as const;
export function Icon({ name }: { name: keyof typeof paths }) {
  return <svg viewBox="0 0 24 24" className="icon" aria-hidden="true" fill="none" stroke="currentColor"
    strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
    {name === "globe" && <circle cx="12" cy="12" r="10" />}
    <path d={paths[name]} />
  </svg>;
}

export function Dial({ glyph }: { glyph?: boolean }) {
  return <span className={glyph ? "dial glyph" : "dial"} aria-hidden="true">
    <svg viewBox="0 0 48 48" fill="none">
      <path d="M10 29a15 15 0 0 1 28 0" stroke="currentColor" strokeWidth="3.5" />
      <path d="m12.5 19.5 4.2 2.6M23.5 13v5M34.7 18.1l-3.3 3.8" stroke="currentColor" strokeWidth="2.4" />
      <g className="dial-needle"><path d="m24 31 9-13" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round"/>
        <circle cx="24" cy="31" r="3.4" fill="currentColor"/></g>
    </svg>
  </span>;
}

function point(value: number, radius: number) {
  const theta = (-180 + value * 1.8) * Math.PI / 180;
  return [140 + Math.cos(theta) * radius, 139 + Math.sin(theta) * radius];
}
function arc(low: number, high: number, radius: number) {
  return `M${point(low, radius).join(" ")} A${radius} ${radius} 0 0 1 ${point(high, radius).join(" ")}`;
}

export function VerdictGauge({ result }: { result: Verdict }) {
  const t = useTranslations("result");
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(result.index);
  useEffect(() => {
    if (reduce) return;
    const animation = animate(0, result.index, { type: "spring", stiffness: 170, damping: 20,
      onUpdate: (n) => setShown(Math.max(0, Math.min(100, Math.round(n)))) });
    return () => animation.stop();
  }, [result.index, reduce]);
  const value = reduce ? result.index : shown;
  return <div className="gauge">
    <svg viewBox="0 0 280 157" aria-hidden="true" fill="none">
      <path d={arc(0, 100, 114)} stroke="var(--paper)" strokeWidth="20" />
      <path d={arc(result.interval.low, result.interval.high, 114)} stroke="var(--ink)" strokeWidth="20" />
      <motion.path d={arc(result.interval.low, result.interval.high, 114)} stroke="var(--accent)" strokeWidth="15"
        initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: reduce ? 0 : 0.3, duration: reduce ? 0 : 0.15 }} />
      {Array.from({ length: 21 }, (_, i) => {
        const a = point(i * 5, 94);
        const b = point(i * 5, i % 5 === 0 ? 81 : 89);
        return <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="var(--ink)" strokeWidth={i % 5 === 0 ? 2.5 : 1} />;
      })}
      <path d="M140 134 138 26l-5 108z" fill="var(--ink)" transform={`rotate(${value * 1.8 - 90} 140 139)`}/>
      <circle cx="140" cy="139" r="8" fill="var(--ink)" />
    </svg>
    <strong data-testid="gauge-value" className="index" aria-label={t("scoreLabel", { index: result.index })}>{value}</strong>
    <span className="interval">{t("range", result.interval)}</span>
  </div>;
}

export function Signals({ result }: { result: Verdict }) {
  const t = useTranslations("result");
  const locale = useLocale();
  return <section aria-labelledby="signals-title" className="signals">
    <h2 id="signals-title">{t("signals")}</h2>
    <div className="signal-grid">{result.signals.map(({ id, value, humanReference, samples }) => {
      const fmt = Intl.NumberFormat(locale, { style: id === "e6" || id === "stylometry" ? "percent" : "decimal", maximumFractionDigits: 2 });
      const min = Math.min(...samples ?? []), max = Math.max(...samples ?? []);
      return <article className="signal-card" key={id}>
        <h3>{t(`${id}.title`)}</h3>
        {samples && <svg viewBox="0 0 140 32" className="sparkline" role="img" aria-label={t("series")}>
          <polyline points={samples.map((v, i) => `${2 + i / (samples.length - 1) * 136},${max === min ? 16 : 29 - (v - min) / (max - min) * 26}`).join(" ")}
            fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>}
        <p>{t(`${id}.detail`)}</p>
        <dl><div><dt>{t("you")}</dt><dd>{fmt.format(value)}</dd></div>
          <div><dt>{t("ref")}</dt><dd>{fmt.format(humanReference)}</dd></div></dl>
      </article>;
    })}</div>
  </section>;
}
