"use client";
import { useLocale, useTranslations } from "next-intl";
import type { CheckResult } from "@vibechecker/contracts";
import { lensVendors, lensIds, lensEvidence, sentenceAudit } from "../lib/lenses";
export function LensPanel({ result }: { result: CheckResult }) {
  const t = useTranslations("lenses");
  const locale = useLocale();
  const lenses = result.lenses;
  return (
    <section className="lens-panel">
      <h2>{t("title")}</h2>
      <p>{t(lenses ? "intro" : "old")}</p>
      {lenses &&
        lensIds.map((id) => {
          const value = lenses[id];
          let label = t("quick");
          let position: number | null = null;
          if (typeof value === "number") {
            label = value + "%";
            position = value;
          } else if (value === "masked") {
            label = t("masked");
          } else if (value) {
            label = t(
              id === "gptzero" ? { low: "human", mixed: "uncertain", high: "ai" }[value] : value,
            );
            position = { low: 10, mixed: 50, high: 90 }[value];
          }
          return (
            <details key={id} className="lens-row">
              <summary>
                <strong>{t("style", { vendor: lensVendors[id] })}</strong>
                <span aria-hidden="true" className="lens-track">
                  {position !== null && <i style={{ left: position + "%" }} />}
                  {value === "masked" && <span className="lens-masked-range" />}
                </span>
                <span className="lens-value">{label}</span>
              </summary>
              <p>
                {t(id)} {lensEvidence[id].within_two_points === false && t("fail")}{" "}
                {lensEvidence[id].target === null && t("qual")}
                {id === "turnitin" &&
                  !sentenceAudit.broad_at_shipped_cutoff.within_two_points &&
                  " " + t("broadMiss")}
              </p>
              <p>{t("disclaimer", { vendor: lensVendors[id] })}</p>
            </details>
          );
        })}
      <a className="text-button" href={`/${locale}/methodology#lenses`}>
        {t("source")}
      </a>
    </section>
  );
}
