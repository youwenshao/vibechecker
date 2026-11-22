"use client";
import type { ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { Mode } from "@vibechecker/contracts";
import { Chop, LensStamp, Riso, Roundel, StampedHolo, StampedStamp } from "./Marks";
import { Flyer, GuestPass, type Reading } from "./ResultObjects";

const sampleQuick: Reading = {
  index: 31,
  interval: { low: 19, high: 44 },
  band: "low",
  wordCount: 412,
  lenses: { version: 1, turnitin: null, gptzero: "low", zerogpt: "mixed", grammarly: "low", veriguide: "low" },
};
const sampleDeep: Reading = {
  index: 62,
  interval: { low: 48, high: 75 },
  band: "mixed",
  wordCount: 1204,
  sentences: [0.12, 0.3, 0.18, 0.72, 0.4, 0.22, 0.9, 0.35, 0.15, 0.55, 0.28, 0.8, 0.2, 0.45, 0.66, 0.1]
    .map((score, i) => ({ start: i * 10, end: i * 10 + 9, score, signals: [] })),
};
const flyerDay = Date.UTC(2026, 10, 18, 4);
const passDay = Date.UTC(2026, 10, 22, 4);

export function HomeTitle() {
  const t = useTranslations("home");
  const locale = useLocale();
  const label = t.markup("title", { br: () => (locale.startsWith("zh") ? "" : " "), nw: (chunks) => chunks, o: (chunks) => chunks });
  const title = (ghost: boolean) => t.rich("title", {
    br: () => <br />,
    nw: (chunks: ReactNode) => <span className="nw">{chunks}</span>,
    o: (chunks: ReactNode) => ghost ? <span className="o" /> : <span className="o">
      <span className="o-quick"><StampedStamp seed={3} fit /></span>
      <span className="o-deep"><StampedHolo fit /></span>
      <span className="sr-only">{chunks}</span>
    </span>,
  });
  return <Riso as="h1" className="home-title mode-riso" label={label} ghost={title(true)}>{title(false)}</Riso>;
}

export function SampleCard({ mode }: { mode: Mode }) {
  const t = useTranslations("home");
  return <aside className="home-side" aria-label={t("sampleLabel")}>
    <div className="flip" aria-hidden="true">
      <div className="flip-inner">
        <div className="flip-face flip-front"><Flyer result={sampleQuick} at={flyerDay} /></div>
        <div className="flip-face flip-back"><GuestPass result={sampleDeep} at={passDay} id="SAMPLE" /></div>
      </div>
    </div>
    <p className="side-cap">{t.rich(mode === "quick" ? "sampleQuick" : "sampleDeep", { b: (chunks) => <b>{chunks}</b> })}</p>
  </aside>;
}

export function DoorSteps() {
  const t = useTranslations();
  return <section className="below" aria-label={t("home.stepsLabel")}>
    <article className="step plate">
      <span className="k"><Roundel word={t("home.stepStampWord")} sub={t("home.stepStampSub")} date="EVERY NIGHT" seed={9} /></span>
      <h2>{t("home.step1Title")}</h2><p>{t("home.step1Body")}</p>
    </article>
    <article className="step plate">
      <span className="k wide"><LensStamp shape="circle" vendor={t("lenses.style", { vendor: "GPTZero" })} value={t("lenses.uncertain")} color="var(--royal-600)" seed={5} /></span>
      <h2>{t("home.step2Title")}</h2><p>{t("home.step2Body")}</p>
    </article>
    <article className="step plate">
      <span className="k"><Chop /></span>
      <h2>{t("home.step3Title")}</h2><p>{t("home.step3Body")}</p>
    </article>
  </section>;
}
