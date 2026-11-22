"use client";
import type { ReactNode, RefObject } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { Mode } from "@vibechecker/contracts";
import type { Stage, Verdict } from "../lib/check-stream";
import { tonightGlyph } from "../lib/brand";
import { CautionText } from "./CautionText";
import { Icon } from "./Icons";
import { Look, Riso, StampedMark, cx } from "./Marks";
import { Flyer, MiniPass, PassStage } from "./ResultObjects";
import { StatusTicker } from "./StatusTicker";

export type Panel = "how" | "why" | "wrong";

export function StatusBox({ stage, done }: { stage?: Stage; done?: boolean }) {
  const t = useTranslations("home");
  return <div className="status-box">
    <span className="status-eyes"><Look happy={done} /></span>
    {done ? <p role="status">{t("done")}</p> : <StatusTicker stage={stage ?? "loading"} />}
  </div>;
}

export function HouseRule({ className }: { className?: string }) {
  const t = useTranslations("result");
  return <aside className={cx("house-rule", className)} aria-label={t("cautionLabel")}>
    <span className="dot"><StampedMark /></span>
    <p><CautionText /></p>
  </aside>;
}

export function ResultHero({ result, mode, at, id, level = 1, titleRef, top, actions, onPanel, issue }: {
  result: Verdict;
  mode: Mode;
  at: number;
  id?: string;
  level?: 1 | 2;
  titleRef?: RefObject<HTMLHeadingElement | null>;
  top?: ReactNode;
  actions?: ReactNode;
  onPanel: (panel: Panel) => void;
  issue?: boolean;
}) {
  const t = useTranslations();
  const deep = mode === "deep";
  const Title = level === 1 ? "h1" : "h2";
  const band = t(`result.bands.${result.band}`);
  const bold = (chunks: ReactNode) => <b>{chunks}</b>;
  return <section className={cx("result-top", !deep && "quick")} aria-labelledby="result-title">
    <div className="result-copy">
      {top}
      <div className="mode-row">
        <span className="mode-chip"><Icon name={deep ? "layers" : "bolt"} />{t(deep ? "result.deepChip" : "result.quickChip")}</span>
        {actions}
      </div>
      <Title id="result-title" ref={titleRef} tabIndex={-1}>{t("result.title")}</Title>
      {deep
        ? (level === 1 ? <h2 className="band-title">{band}</h2> : <h3 className="band-title">{band}</h3>)
        : <Riso as={level === 1 ? "h2" : "h3"} className="band-title billing">{band}</Riso>}
      <p className="interp">{t(`result.interpretation.${result.band}`)}</p>
      <p className="reading">
        <span>{t.rich("result.outOf", { index: result.index, b: bold })}</span>
        <span>{t.rich("result.likely", { low: result.interval.low, high: result.interval.high, b: bold })}</span>
        <span>{t("home.count", { n: result.wordCount })}</span>
      </p>
      <div className="why">
        {(["why", "wrong"] as const).map((name) => <button type="button" className="pill" key={name} onClick={() => onPanel(name)}>
          <Icon name={name === "why" ? "question" : "info"} />{t(`result.${name}`)}</button>)}
      </div>
    </div>
    {deep
      ? <PassStage result={result} at={at} id={id} issue={issue} testId="gauge-value" />
      : <div className="result-flyer"><Flyer result={result} at={at} print={issue} testId="gauge-value" /></div>}
  </section>;
}

export function Flags({ result }: { result: Verdict }) {
  const t = useTranslations("result");
  if (!result.flags.length) return null;
  return <section className="flags plate" aria-labelledby="flags-title">
    <h2 id="flags-title">{t("flags")}</h2>
    <ul>{result.flags.map((flag) => <li key={flag}>{t(flag)}</li>)}</ul>
  </section>;
}

const sampleHeats = [0.12, 0.3, 0.18, 0.72, 0.4, 0.22, 0.9, 0.35, 0.15, 0.55, 0.28, 0.8, 0.2, 0.45];

export function Upsell({ onDeep, at }: { onDeep: () => void; at: number }) {
  const t = useTranslations("result");
  return <section className="upsell plate" aria-labelledby="upsell-title">
    <MiniPass index={62} heats={sampleHeats} glyph={tonightGlyph(at)} />
    <div>
      <span className="eyebrow">{t("upsellEyebrow")}</span>
      <h2 id="upsell-title">{t("upsellTitle")}</h2>
      <p>{t("upsellBody")}</p>
    </div>
    <button type="button" className="btn btn-primary" onClick={onDeep}><Icon name="layers" />{t("upsellAction")}</button>
  </section>;
}

export function InfoDialog({ panel, dialog }: { panel: Panel; dialog: RefObject<HTMLDialogElement | null> }) {
  const t = useTranslations();
  const locale = useLocale();
  return <dialog ref={dialog} aria-labelledby="panel-title">
    <div className="dialog-head">
      <h2 id="panel-title">{panel === "how" ? t("chrome.how") : t(`result.${panel}`)}</h2>
      <button type="button" className="circle-button" onClick={() => dialog.current?.close()} aria-label={t("chrome.close")}><Icon name="close" /></button>
    </div>
    <p>{panel === "how" ? t("home.howBody") : t(`result.${panel}Body`)}</p>
    <a className="text-link" href={`/${locale}/methodology`}>{t("chrome.methodology")}<Icon name="arrow" /></a>
  </dialog>;
}
