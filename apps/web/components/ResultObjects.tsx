"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { Verdict } from "../lib/check-stream";
import { deviceTtl } from "../lib/device";
import { lensIds, lensVendors } from "../lib/lenses";
import { flyerDate, machineLines, passDate, sentenceHeats, stampDate, tonightGlyph, type Glyph } from "../lib/brand";
import type { PassScene } from "../lib/pass3d";
import { Guilloche, Riso, Roundel, Seal, SentencePrint, StampedMark, StampedStamp, cx } from "./Marks";
import { useLensReading } from "./LensPanel";

export type Reading = Pick<Verdict, "index" | "interval" | "band" | "wordCount" | "lenses" | "sentences">;
type ObjectProps = { result: Reading; at: number; testId?: string };

const foil = "VIBECHECKER · 已檢 · VIBECHECKER · 已檢 · VIBECHECKER";
const mrz = (line: string) => line.padEnd(33, "<").slice(0, 33);

export function Flyer({ result, at, print, testId }: ObjectProps & { print?: boolean }) {
  const t = useTranslations();
  const read = useLensReading();
  const lenses = result.lenses;
  return <div className={cx("flyer", print && "print")} aria-hidden="true">
    <div className="flyer-sheet">
      <div className="flyer-top">
        <Riso className="wordmark">{t("chrome.brand")}</Riso>
        <p>{flyerDate(at)}<br />{t("home.quick")}<br />{t("home.count", { n: result.wordCount })}</p>
      </div>
      <p className="flyer-label">{t("result.title")}</p>
      <div className="flyer-score" data-len={String(result.index).length}>
        <Riso as="p" className="flyer-num" testId={testId}>{result.index}</Riso>
        <span className="flyer-blob"><StampedStamp seed={4} /></span>
      </div>
      <Riso as="p" className="flyer-billing">{t(`result.bands.${result.band}`).split(" ").map((word, i) =>
        <span className="w" key={i}>{word}</span>)}</Riso>
      <span className="flyer-range"><span>{t("result.rangeLabel")}</span><span>{result.interval.low}–{result.interval.high}</span></span>
      {lenses && <ul className="lineup">{lensIds.map((id) => {
        const reading = read(id, lenses[id]);
        return <li key={id} className={reading.off ? "off" : undefined}>
          <span>{t("lenses.style", { vendor: lensVendors[id] })}</span><span>{reading.short}</span>
        </li>;
      })}</ul>}
      <p className="flyer-fine">{t("chrome.foot")}</p>
    </div>
  </div>;
}

function useStampWords(band: Reading["band"]) {
  const t = useTranslations("result");
  return { word: t(`stampWord.${band}`), sub: t(`stampSub.${band}`) };
}

export function GuestPass({ result, at, id, issue, testId }: ObjectProps & { id?: string; issue?: boolean }) {
  const t = useTranslations();
  const locale = useLocale();
  const stamp = useStampWords(result.band);
  const { low, high } = result.interval;
  const range = { "--lo": low + "%", "--hi": high + "%", "--at": result.index + "%" } as CSSProperties;
  const [first, second] = machineLines(result, at, id);
  return <div className={cx("pass", issue && "issue")} aria-hidden="true">
    <div className="pass-tilt">
      <div className="pass-card">
        <Guilloche />
        <span className="pass-slot" />
        <div className="pass-top">
          <span className="pass-brand">{t("chrome.brand")}<span className="dot"><StampedMark /></span></span>
          <span className="pass-kind">{t("result.passKind")}</span>
        </div>
        <div className="pass-photo">
          <figure className="pass-portrait"><SentencePrint heats={sentenceHeats(result.sentences)} /><figcaption>{t("result.print")}</figcaption></figure>
          <span className="pass-seal"><Seal glyph={tonightGlyph(at)} /></span>
        </div>
        <dl className="pass-fields">
          <div className="f-index"><dt>{t("result.title")}</dt><dd><strong data-testid={testId}>{result.index}</strong><span>/100</span></dd></div>
          <div className="f-range"><dt>{t("result.rangeLabel")}</dt><dd><span>{low}–{high}</span><span className="rangebar" style={range}><b /><i /></span></dd></div>
          <div className="f-band"><dt>{t("result.bandLabel")}</dt><dd>{t(`result.bands.${result.band}`)}</dd></div>
          <div className="f-mode"><dt>{t("result.modeLabel")}</dt><dd>{t("result.deepShort")}</dd></div>
          <div className="f-words"><dt>{t("result.wordsLabel")}</dt><dd>{new Intl.NumberFormat(locale).format(result.wordCount)}</dd></div>
          <div className="f-iss"><dt>{t("result.issued")}</dt><dd>{passDate(at, locale)}</dd></div>
          <div className="f-keep"><dt>{t("result.kept")}</dt><dd>{passDate(at + deviceTtl, locale)}</dd></div>
        </dl>
        <div className="pass-foil"><span>{foil}</span></div>
        <p className="pass-mrz"><span>{mrz(first)}</span><span>{mrz(second)}</span></p>
        <span className="pass-glare" />
      </div>
      <div className="stamp"><Roundel word={stamp.word} sub={stamp.sub} date={stampDate(at)} seed={5} /></div>
    </div>
  </div>;
}

export function PassStage(props: ObjectProps & { id?: string; issue?: boolean }) {
  const { result, at, id } = props;
  const t = useTranslations();
  const locale = useLocale();
  const stamp = useStampWords(result.band);
  const host = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "flat" | "live">("loading");
  const scene: PassScene = {
    index: result.index,
    low: result.interval.low,
    high: result.interval.high,
    heats: sentenceHeats(result.sentences),
    glyph: tonightGlyph(at),
    mrz: machineLines(result, at, id),
    stamp: { ...stamp, date: stampDate(at) },
    text: {
      kind: t("result.passKind"),
      print: t("result.print"),
      title: t("result.title"),
      range: t("result.rangeLabel"),
      fields: [
        [t("result.bandLabel"), t(`result.bands.${result.band}`)],
        [t("result.modeLabel"), t("result.deepShort")],
        [t("result.wordsLabel"), new Intl.NumberFormat(locale).format(result.wordCount)],
        [t("result.issued"), passDate(at, locale)],
        [t("result.kept"), passDate(at + deviceTtl, locale)],
      ],
      caution: t("chrome.foot"),
      keep: t("result.passKeep"),
      footer: t("result.passNotProof"),
    },
  };
  const key = JSON.stringify(scene);
  useEffect(() => {
    const stage = host.current;
    if (!stage) return;
    let live = true;
    let stop: (() => void) | null = null;
    setState("loading");
    const reveal = window.setTimeout(() => live && setState((now) => (now === "loading" ? "flat" : now)), 1500);
    import("../lib/pass3d")
      .then(({ mount }) => mount(stage, JSON.parse(key) as PassScene))
      .then((dispose) => {
        if (!live) return dispose?.();
        stop = dispose;
        setState(dispose ? "live" : "flat");
      }, () => live && setState("flat"))
      .finally(() => window.clearTimeout(reveal));
    return () => {
      live = false;
      window.clearTimeout(reveal);
      stop?.();
    };
  }, [key]);
  return <div ref={host} className={cx("stage", state === "loading" && "loading", state === "live" && "is-3d")}>
    <div className="stage-fallback"><GuestPass {...props} /></div>
    <p className="stage-hint" aria-hidden="true">{t("result.swing")}</p>
  </div>;
}

export function MiniPass({ index, heats, glyph }: { index: number; heats: number[]; glyph: Glyph }) {
  const t = useTranslations("result");
  return <div className="mini" aria-hidden="true">
    <b>{index}</b><small>{t("passKind")}</small>
    <span className="print"><SentencePrint heats={heats} /></span>
    <span className="seal"><Seal glyph={glyph} /></span>
  </div>;
}

export function ThumbPass({ index, heats, glyph }: { index?: number | null; heats: number[]; glyph: Glyph }) {
  return <span className="thumb thumb-pass" aria-hidden="true">
    <b>{index ?? "–"}</b>
    <span className="print"><SentencePrint heats={heats} /></span>
    <span className="seal"><Seal glyph={glyph} /></span>
  </span>;
}

export function ThumbFlyer({ index, band }: { index?: number | null; band?: string }) {
  return <span className="thumb thumb-flyer" aria-hidden="true">
    <span className="blob"><StampedStamp seed={4} /></span>
    <span className="n">{index ?? "–"}</span>
    {band && <small>{band}</small>}
  </span>;
}
