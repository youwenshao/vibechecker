"use client";
import { Fragment, useId, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { useTranslations } from "next-intl";
import type { SentenceScore, SignalId } from "@vibechecker/contracts";
import { Icon } from "./Icons";
import { cx } from "./Marks";

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
  const [lights, setLights] = useState(false);
  const group = useRef<HTMLDivElement>(null);
  const signals = [...new Set(sentences.flatMap((item) => item.signals))].sort();
  const visible = (item: SentenceScore) => filter === "all" || item.signals.includes(filter);
  const active = sentences.find((item) => item.start === selected && visible(item));
  const matched = sentences.filter(visible).length;
  const firstStart = sentences.find(visible)?.start;
  const sentenceSignals = (item: SentenceScore) => item.signals.length
    ? item.signals.map((signal) => t(`result.${signal}.title`)).join(t("heat.separator")) : t("heat.none");

  function navigate(event: KeyboardEvent<HTMLSpanElement>, start: number) {
    if (event.key === "Escape") { setSelected(undefined); return; }
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelected(start); return; }
    const buttons = Array.from(group.current?.querySelectorAll<HTMLSpanElement>("[data-start]") ?? []);
    const index = buttons.indexOf(event.currentTarget);
    const next = { ArrowLeft: index - 1, ArrowUp: index - 1, ArrowRight: index + 1,
      ArrowDown: index + 1, Home: 0, End: buttons.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    buttons[Math.min(buttons.length - 1, Math.max(0, next))]?.focus();
  }

  function torch(event: PointerEvent<HTMLDivElement>) {
    if (event.pointerType !== "mouse" || lights || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const box = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--tx", `${event.clientX - box.left}px`);
    event.currentTarget.style.setProperty("--ty", `${event.clientY - box.top}px`);
  }

  function marker(item: DisplaySentence, index: number) {
    const band = strength(item.score);
    const sentence = text.slice(item.start, item.end);
    return <span role="button" lang="en" data-start={item.start} data-strength={band}
      className="sentence-marker" style={{ "--sweep-delay": `${streaming ? (item.stagger ?? 0) * 30 : 0}ms` } as CSSProperties}
      aria-label={t("heat.sentenceLabel", { n: index + 1, sentence, band: t(`heat.${band}`) })}
      aria-describedby={active?.start === item.start ? id + "-detail" : undefined}
      tabIndex={item.start === (active?.start ?? firstStart) ? 0 : -1}
      onKeyDown={(event) => navigate(event, item.start)} onFocus={() => setSelected(item.start)} onClick={() => setSelected(item.start)}
      onPointerEnter={(event) => { if (event.pointerType === "mouse") setSelected(item.start); }}>
      {sentence}</span>;
  }

  return <section className="section heatmap" aria-labelledby={`${id}-eyebrow ${id}-title`}>
    <div className="section-head">
      <div>
        <span className="eyebrow" id={id + "-eyebrow"}>{t("heat.eyebrow")}</span>
        <h2 id={id + "-title"}>{t("heat.title")}</h2>
        <p className="heat-count" aria-live="polite" aria-atomic="true">{t(streaming ? "heat.analyzed" : "heat.count", { n: sentences.length })}</p>
      </div>
      <p>{t("heat.intro")}</p>
    </div>
    <div className={cx("uv", lights && "lights", streaming && "streaming")} onPointerMove={torch}>
      <span className="torch" aria-hidden="true" />
      <div className="uv-bar">
        <ul aria-label={t("heat.strength")} className="heat-key">
          {(["faint", "moderate", "strong"] as const).map((band) =>
            <li key={band}><span className="sw" data-strength={band} aria-hidden="true">Aa</span>{t(`heat.${band}`)}</li>)}
        </ul>
        <div className="uv-tools">
          <div className="uv-filter">
            <label htmlFor={id + "-filter"} className="sr-only">{t("heat.filter")}</label>
            <select id={id + "-filter"} value={filter} onChange={(e) => { setFilter(e.target.value as typeof filter); setSelected(undefined); }}>
              <option value="all">{t("heat.all")}</option>
              {signals.map((signal) => <option key={signal} value={signal}>{t(`result.${signal}.title`)}</option>)}
            </select>
            {filter !== "all" && <span className="uv-matches">{t("heat.matches", { n: matched })}</span>}
          </div>
          <div className="view-switch" role="group" aria-label={t("heat.view")}>
            {(["passage", "list"] as const).map((choice) => <button type="button" key={choice} aria-pressed={view === choice}
              onClick={() => setView(choice)}>{t(`heat.${choice}`)}</button>)}
          </div>
          <button type="button" className="lights-btn" aria-pressed={lights} onClick={() => setLights((on) => !on)}>
            <Icon name="bulb" />{t("heat.lights")}</button>
        </div>
      </div>
      <div className="uv-body">
        <div ref={group} className="essay-sheet" dir="auto">
          {view === "passage" ? <p lang="en">{sentences.map((item, i) => <Fragment key={item.start}>
            {text.slice(i ? sentences[i - 1].end : 0, item.start)}
            {visible(item) ? marker(item, i) : text.slice(item.start, item.end)}
          </Fragment>)}{text.slice(sentences.at(-1)?.end ?? 0)}</p>
          : <ol className="sentence-list">{sentences.map((item, i) => visible(item) && <li key={item.start} value={i + 1}>
            {marker(item, i)}<span className="list-note">{t(`heat.${strength(item.score)}`)} · {sentenceSignals(item)}</span>
          </li>)}</ol>}
        </div>
        <div className="tip-col">
          {active ? <div className="tip" role="tooltip" id={id + "-detail"}>
            <p className="tip-kicker">{t("heat.detail", { n: sentences.indexOf(active) + 1 })}</p>
            <p className="tip-title">{t(`heat.${strength(active.score)}`)}</p>
            {active.signals.length
              ? <ul>{active.signals.map((signal) => <li key={signal}>{t(`result.${signal}.title`)}</li>)}</ul>
              : <p className="tip-none">{t("heat.none")}</p>}
          </div> : <div className="tip"><p className="heat-help">{t("heat.help")}</p></div>}
        </div>
      </div>
    </div>
  </section>;
}
