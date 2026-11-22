"use client";
import type { CSSProperties } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { CheckResult, Mode } from "@vibechecker/contracts";
import { lensEvidence, lensIds, lensVendors, sentenceAudit, type LensId } from "../lib/lenses";
import { Icon } from "./Icons";
import { LensStamp, cx, type LensShape } from "./Marks";

type Lenses = NonNullable<CheckResult["lenses"]>;
export type LensReading = { label: string; short: string; off: boolean };

export function useLensReading() {
  const t = useTranslations("lenses");
  return (id: LensId, value: Lenses[LensId]): LensReading => {
    if (typeof value === "number") return { label: value + "%", short: value + "%", off: false };
    if (value === "masked") return { label: t("masked"), short: "*%", off: false };
    if (!value) return { label: t("deepOnly"), short: t("deepOnly"), off: true };
    const label = t(id === "gptzero" ? { low: "human", mixed: "uncertain", high: "ai" }[value] : value);
    return { label, short: label, off: false };
  };
}

const visa: Record<LensId, { shape: LensShape; color: string; tilt: number; seed: number }> = {
  turnitin: { shape: "rect", color: "var(--royal-600)", tilt: -5, seed: 3 },
  gptzero: { shape: "circle", color: "var(--magenta-600)", tilt: 6, seed: 5 },
  zerogpt: { shape: "octagon", color: "var(--lilac-700)", tilt: 3, seed: 8 },
  grammarly: { shape: "oval", color: "var(--royal-600)", tilt: -7, seed: 11 },
  veriguide: { shape: "hex", color: "var(--magenta-600)", tilt: 4, seed: 13 },
};

export function LensPanel({ result, mode, onDeep }: { result: CheckResult; mode: Mode; onDeep?: () => void }) {
  const t = useTranslations("lenses");
  const action = useTranslations("result");
  const locale = useLocale();
  const read = useLensReading();
  const lenses = result.lenses;
  const deep = mode === "deep";
  const source = <a className="text-link" href={`/${locale}/methodology#lenses`}>{t("source")}<Icon name="arrow" /></a>;
  return <section className="section" aria-labelledby="policies-title">
    <div className="section-head">
      <div><span className="eyebrow">{t("eyebrow")}</span><h2 id="policies-title">{t("title")}</h2></div>
      <p>{t(lenses ? "intro" : "old")}</p>
    </div>
    {lenses && <ul className={cx("policies", deep ? "visa plates" : "plate")}>
      {lensIds.map((id) => {
        const vendor = lensVendors[id];
        const name = t("style", { vendor });
        const reading = read(id, lenses[id]);
        const evidence = lensEvidence[id];
        return <li key={id}><details className={cx("lens-row", reading.off && "off")}>
          <summary>
            {deep && <span className="visa-stamp" style={{ "--r": visa[id].tilt + "deg" } as CSSProperties}>
              <LensStamp shape={visa[id].shape} vendor={name} value={reading.short} color={visa[id].color} seed={visa[id].seed} />
            </span>}
            <span className="p-name">{name}</span>
            <span className="p-read">{reading.label}</span>
            <span className="p-gist">{reading.off ? t("quick") : t(`${id}Gist`)}</span>
            <span className="p-more" aria-hidden="true">+</span>
          </summary>
          <div className="p-body">
            <p>{t(id)} {evidence.within_two_points === false && t("fail")}{" "}
              {evidence.target === null && t("qual")}
              {id === "turnitin" && !sentenceAudit.broad_at_shipped_cutoff.within_two_points && " " + t("broadMiss")}</p>
            <p>{t("disclaimer", { vendor })}</p>
            {reading.off && onDeep && <button type="button" className="btn btn-quiet" onClick={onDeep}>
              <Icon name="layers" />{action("upsellAction")}</button>}
          </div>
        </details></li>;
      })}
      {deep && <li className="visa-note"><p>{t("note")}</p>{source}</li>}
    </ul>}
    {(!deep || !lenses) && <p className="policy-note">{lenses && t("note")} {source}</p>}
  </section>;
}
