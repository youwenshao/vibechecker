"use client";
import type { CSSProperties } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { Verdict } from "../lib/check-stream";

function Sparkline({ samples, label }: { samples: number[]; label: string }) {
  const min = Math.min(...samples);
  const max = Math.max(...samples);
  return <svg viewBox="0 0 140 32" className="sparkline" role="img" aria-label={label} preserveAspectRatio="none">
    <polyline points={samples.map((v, i) => `${2 + (i / Math.max(1, samples.length - 1)) * 136},${max === min ? 16 : 29 - ((v - min) / (max - min)) * 26}`).join(" ")}
      fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
  </svg>;
}

export function Signals({ result }: { result: Verdict }) {
  const t = useTranslations("result");
  const locale = useLocale();
  return <section className="section" aria-labelledby="signals-title">
    <div className="section-head">
      <div><span className="eyebrow">{t("signalsEyebrow")}</span><h2 id="signals-title">{t("signals")}</h2></div>
      <p>{t("signalsIntro")}</p>
    </div>
    <div className="notes-row plates">{result.signals.map(({ id, value, humanReference, samples }) => {
      const format = new Intl.NumberFormat(locale, { style: id === "e6" || id === "stylometry" ? "percent" : "decimal", maximumFractionDigits: 2 });
      const gap = humanReference ? (value - humanReference) / Math.abs(humanReference) : value;
      const you = { "--you": 50 + Math.max(-44, Math.min(44, gap * 50)) + "%" } as CSSProperties;
      return <article className="note" key={id}>
        <h3>{t(`${id}.title`)}</h3>
        <p>{t(`${id}.detail`)}</p>
        {samples && samples.length > 1 && <Sparkline samples={samples} label={t("series")} />}
        <div className="cmp" style={you} aria-hidden="true"><i className="ref" /><i className="you" /></div>
        <dl>
          <div><dt>{t("you")}</dt><dd>{format.format(value)}</dd></div>
          <div><dt>{t("ref")}</dt><dd>{format.format(humanReference)}</dd></div>
        </dl>
      </article>;
    })}</div>
  </section>;
}
