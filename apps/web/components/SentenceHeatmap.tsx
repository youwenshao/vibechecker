"use client";
import { Fragment, useId, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { useTranslations } from "next-intl";
import type { SentenceScore, SignalId } from "@vibechecker/contracts";

export type DisplaySentence = SentenceScore & { stagger?: number };
type Props = { text: string; sentences: DisplaySentence[]; streaming: boolean };
function strength(score: number) {
  return score >= 2 / 3 ? "strong" : score >= 1 / 3 ? "moderate" : "faint";
}

export function SentenceHeatmap({ text, sentences, streaming }: Props) {
  const t = useTranslations();
  const id = useId();
  const [view, setView] = useState<"passage" | "list">("passage");
  const [filter, setFilter] = useState<SignalId | "all">("all");
  const [selected, setSelected] = useState<number>();
  const group = useRef<HTMLDivElement>(null);
  const signals = [...new Set(sentences.flatMap((item) => item.signals))].sort();
  const visible = (item: SentenceScore) => filter === "all" || item.signals.includes(filter);
  const active = sentences.find((item) => item.start === selected && visible(item));
  const matched = sentences.filter(visible).length;
  const firstStart = sentences.find(visible)?.start;
  const sentenceSignals = (item: SentenceScore) => item.signals.length
    ? item.signals.map((signal) => t(`result.${signal}.title`)).join(t("heat.separator")) : t("heat.none");

  function navigate(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "Escape") { setSelected(undefined); return; }
    const buttons = Array.from(group.current?.querySelectorAll<HTMLButtonElement>("button[data-start]") ?? []);
    const index = buttons.indexOf(event.currentTarget);
    const next = { ArrowLeft: index - 1, ArrowUp: index - 1, ArrowRight: index + 1,
      ArrowDown: index + 1, Home: 0, End: buttons.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    buttons[Math.min(buttons.length - 1, Math.max(0, next))]?.focus();
  }

  function marker(item: DisplaySentence, index: number) {
    const band = strength(item.score);
    const sentence = text.slice(item.start, item.end);
    return <button type="button" lang="en" data-start={item.start} data-strength={band}
      className="sentence-marker" style={{ "--sweep-delay": `${streaming ? (item.stagger ?? 0) * 30 : 0}ms` } as CSSProperties}
      aria-label={t("heat.sentenceLabel", { n: index + 1, sentence, band: t(`heat.${band}`) })}
      aria-describedby={active?.start === item.start ? id + "-detail" : undefined}
      tabIndex={item.start === (active?.start ?? firstStart) ? 0 : -1}
      onKeyDown={navigate} onFocus={() => setSelected(item.start)} onClick={() => setSelected(item.start)}
      onPointerEnter={(event) => { if (event.pointerType === "mouse") setSelected(item.start); }}>
      {sentence}</button>;
  }

  return <section className="heatmap" aria-labelledby={id + "-title"}>
    <div className="heat-header">
      <div><h2 id={id + "-title"}>{t("heat.title")}</h2>
        <p className="heat-count" aria-live="polite" aria-atomic="true">{t(streaming ? "heat.analyzed" : "heat.count", { n: sentences.length })}</p></div>
      <div className="view-switch" role="group" aria-label={t("heat.view")}>
        {(["passage", "list"] as const).map((choice) => <button type="button" key={choice} aria-pressed={view === choice}
          onClick={() => setView(choice)}>{t(`heat.${choice}`)}</button>)}
      </div>
    </div>
    <div className="heat-grid">
      <div ref={group} className="essay-sheet" dir="auto">
        {view === "passage" ? <p lang="en">{sentences.map((item, i) => <Fragment key={item.start}>
          {text.slice(i ? sentences[i - 1].end : 0, item.start)}
          {visible(item) ? marker(item, i) : text.slice(item.start, item.end)}
        </Fragment>)}{text.slice(sentences.at(-1)?.end ?? 0)}</p>
        : <ol className="sentence-list">{sentences.map((item, i) => visible(item) && <li key={item.start} value={i + 1}>
          {marker(item, i)}<span className="list-note">{t(`heat.${strength(item.score)}`)} · {sentenceSignals(item)}</span>
        </li>)}</ol>}
      </div>
      <aside className="heat-inspector">
        <label htmlFor={id + "-filter"}>{t("heat.filter")}</label>
        <select id={id + "-filter"} value={filter} onChange={(e) => { setFilter(e.target.value as typeof filter); setSelected(undefined); }}>
          <option value="all">{t("heat.all")}</option>
          {signals.map((signal) => <option key={signal} value={signal}>{t(`result.${signal}.title`)}</option>)}
        </select>
        {filter !== "all" && <p>{t("heat.matches", { n: matched })}</p>}
        <ul aria-label={t("heat.strength")} className="heat-key">
          {(["faint", "moderate", "strong"] as const).map((band) =>
            <li key={band}><span className="heat-swatch" data-strength={band}/>{t(`heat.${band}`)}</li>)}
        </ul>
        {active ? <div className="heat-detail" role="tooltip" id={id + "-detail"}>
          <strong>{t("heat.detail", { n: sentences.indexOf(active) + 1 })}</strong>
          <p>{t(`heat.${strength(active.score)}`)} · {sentenceSignals(active)}</p>
        </div> : <p className="heat-help">{t("heat.help")}</p>}
      </aside>
    </div>
  </section>;
}
