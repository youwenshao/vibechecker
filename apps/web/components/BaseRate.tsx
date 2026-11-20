"use client";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";

export function BaseRate() {
  const t = useTranslations("method");
  const locale = useLocale();
  const [prevalence, setPrevalence] = useState(10);
  const aiFlags = prevalence * 10 * 0.8;
  const humanFlags = (1000 - prevalence * 10) * 0.02;
  const share = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(aiFlags / (aiFlags + humanFlags));
  return <div className="prior-demo">
    <p>{t("example")}</p>
    <label htmlFor="prevalence">{t("aiShare")}</label>
    <select id="prevalence" value={prevalence} onChange={(e) => setPrevalence(Number(e.target.value))}>
      {[5, 10, 50].map((n) => <option key={n} value={n}>{n}%</option>)}
    </select>
    <p role="status">{t("exampleResult", { aiFlags, humanFlags, share })}</p>
  </div>;
}
