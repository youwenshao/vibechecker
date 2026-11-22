"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { MotionConfig } from "motion/react";
import { useTranslations } from "next-intl";
import type { Mode } from "@vibechecker/contracts";
import { readEssay, wordCount } from "../lib/essay";
import { CheckError, checkEssay, type Stage } from "../lib/check-stream";
import { deviceTtl, forgetChecks, latestCheck, saveCheck, type DeviceCheck } from "../lib/device";
import { Masthead, SiteFooter } from "./Chrome";
import { EvidenceKit, KitSection } from "./EvidenceKit";
import { DoorSteps, HomeTitle, SampleCard } from "./Home";
import { Icon } from "./Icons";
import { Signals } from "./Instruments";
import { LensPanel } from "./LensPanel";
import { Band } from "./Marks";
import { Flags, HouseRule, InfoDialog, ResultHero, StatusBox, Upsell, type Panel } from "./ResultView";
import { SentenceHeatmap, type DisplaySentence } from "./SentenceHeatmap";
import { Verification } from "./Verification";

type Quota = { owner: string | null; usage: Record<Mode, number>; limits: Record<Mode, number> };

async function readQuota(): Promise<Quota | null> {
  const response = await fetch("/api/quota", { cache: "no-store" });
  return response.ok ? response.json() : null;
}
type ErrorKey = "too_short" | "too_long" | "not_english" | "quota" | "turnstile" | "busy" | "internal" | "file" | "auth_required";
const errors = new Set<ErrorKey>(["too_short", "too_long", "not_english", "quota", "turnstile", "busy", "internal", "file", "auth_required"]);
const modeEnd = "M14 .6H6L1.5 6.6l4.5 6-4.5 6 4.5 6-4.5 6 4.5 6-4.5 6 4.5 5.8h8";

export function Checker() {
  const t = useTranslations();
  const [text, setText] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState<Mode>("quick");
  const [sentences, setSentences] = useState<DisplaySentence[]>([]);
  const minimum = mode === "quick" ? 150 : 300;
  const maximum = mode === "quick" ? 5000 : 2500;
  const [token, setToken] = useState("");
  const [quota, setQuota] = useState<Quota>();
  const [saveText, setSaveText] = useState(false);
  const [challenge, setChallenge] = useState(0);
  const [error, setError] = useState<ErrorKey>();
  const [storageError, setStorageError] = useState<"storageError" | "forgetError">();
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [stage, setStage] = useState<Stage>("loading");
  const [saved, setSaved] = useState<DeviceCheck>();
  const [editing, setEditing] = useState(false);
  const [fresh, setFresh] = useState(false);
  const [panel, setPanel] = useState<Panel>("why");
  const progressTitle = useRef<HTMLHeadingElement>(null);
  const resultTitle = useRef<HTMLHeadingElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const touched = useRef(false);
  const words = wordCount(text);
  const result = editing ? undefined : saved?.result;
  const resultMode = saved?.mode ?? "quick";

  useEffect(() => {
    let mounted = true;
    readQuota().catch(() => null).then(async (current) => {
      if (mounted && current) setQuota(current);
      const check = await latestCheck(current?.owner);
      if (mounted && !touched.current && check) {
        setSaved(check);
        setText(check.text);
        setMode(check.mode ?? "quick");
      }
    }).catch(() => {});
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    if (result && touched.current && !document.activeElement?.closest(".heatmap")) resultTitle.current?.focus();
  }, [result]);

  useEffect(() => { if (busy) progressTitle.current?.focus(); }, [busy]);

  function openPanel(value: Panel) {
    setPanel(value);
    dialog.current?.showModal();
  }

  async function loadFile(input?: File) {
    if (!input) return;
    touched.current = true;
    setReading(true);
    setError(undefined);
    try {
      setText(await readEssay(input));
      box.current?.focus();
    } catch { setError("file"); }
    finally {
      setReading(false);
      if (file.current) file.current.value = "";
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || reading || !token || words < minimum || words > maximum) return;
    touched.current = true;
    setBusy(true);
    setError(undefined);
    setStorageError(undefined);
    setStage("loading");
    setSentences([]);
    try {
      const receipt = await checkEssay(text, mode, token, {
        stage: setStage,
        sentences: (items) => setSentences((prev) => [...prev, ...items.map((item, i) => ({ ...item, stagger: i }))]),
        reset: () => { setSentences([]); setAttempt((n) => n + 1); },
      }, saveText && Boolean(quota?.owner));
      const now = Date.now();
      const check = { ...receipt, mode, text, createdAt: now, expiresAt: now + deviceTtl };
      try { await saveCheck(check); } catch { setStorageError("storageError"); }
      setEditing(false);
      setFresh(true);
      setSaved(check);
    } catch (e) {
      const code = e instanceof CheckError ? e.code as ErrorKey : "internal";
      setError(errors.has(code) ? code : "internal");
    } finally {
      readQuota().then((current) => {
        if (current) setQuota(current);
      }).catch(() => {});
      setSaveText(false);
      setSentences([]);
      setToken("");
      setChallenge((n) => n + 1);
      setBusy(false);
    }
  }

  async function forget() {
    touched.current = true;
    try { await forgetChecks(); }
    catch { setStorageError("forgetError"); return; }
    setSaved(undefined);
    setEditing(false);
    setFresh(false);
    setText("");
    setError(undefined);
    setStorageError(undefined);
    requestAnimationFrame(() => box.current?.focus());
  }

  function edit(next?: Mode) {
    touched.current = true;
    setEditing(true);
    setFresh(false);
    if (next) {
      setMode(next);
      setToken("");
      setError(undefined);
    }
    requestAnimationFrame(() => box.current?.focus());
  }

  const left = (choice: Mode) => quota ? Math.max(0, quota.limits[choice] - quota.usage[choice]) : 0;
  const band = (choice: Mode) => quota && <Band total={quota.limits[choice]} used={quota.limits[choice] - left(choice)}>
    {t(choice === "quick" ? "home.quotaQuick" : "home.quotaDeep", { left: left(choice), limit: quota.limits[choice] })}
  </Band>;
  const gate = words > maximum ? t("errors.too_long", { n: maximum })
    : words > 0 && words < minimum ? t(mode === "quick" ? "home.more" : "home.moreDeep", { n: minimum - words })
    : words >= minimum ? t(token ? (mode === "quick" ? "home.ready" : "home.readyDeep") : "home.verification") : null;
  const forgetButton = <button type="button" className="btn btn-quiet" disabled={busy || reading} onClick={() => void forget()}>
    <Icon name="trash" />{t("home.forget")}</button>;
  const savedNote = storageError ? t(`home.${storageError}`) : t("result.saved");

  const home = <>
    <div className="home-grid">
      <div>
        <HomeTitle />
        <p className="sub">{t("home.subline")}</p>
        <form className="editor plate" onSubmit={submit}>
          <div className="editor-top">
            <fieldset className="modes mode-picker" disabled={busy || reading}>
              <legend className="sr-only">{t("home.mode")}</legend>
              {(["quick", "deep"] as const).map((choice) => <label className="mode" key={choice}>
                <input type="radio" name="mode" value={choice} checked={mode === choice} onChange={() => {
                  touched.current = true; setMode(choice); setToken(""); setError(undefined);
                }} />
                <svg className="mode-end" viewBox="0 0 14 48" preserveAspectRatio="none" aria-hidden="true" focusable="false"><path d={modeEnd} /></svg>
                <b>{t(`home.${choice}`)}</b>
                <small><span>{t(choice === "quick" ? "home.quickTag" : "home.deepTag")}</span><span className="sep"> · </span>
                  <span>{t(choice === "quick" ? "home.quickRange" : "home.deepRange")}</span></small>
              </label>)}
            </fieldset>
            <input ref={file} type="file" accept=".txt,.md,.docx" className="file-input" tabIndex={-1} aria-label={t("home.fileHelp")}
              onChange={(event) => void loadFile(event.target.files?.[0])} />
            <button type="button" className="btn btn-quiet upload" disabled={busy || reading} onClick={() => file.current?.click()}
              title={t("home.fileHelp")}><Icon name="attach" />{t("home.upload")}</button>
          </div>
          <div className="field">
            <label className="sr-only" htmlFor="essay">{t("home.label")}</label>
            <textarea ref={box} id="essay" value={text} onChange={(event) => {
              touched.current = true; setText(event.target.value); setError(undefined);
            }} disabled={busy || reading} placeholder={t("home.placeholder")} aria-describedby="word-limits word-count" dir="auto" />
            <span className="limits" id="word-limits">{t(mode === "deep" ? "home.deepLimits" : "home.limits", { n: minimum })}</span>
            <span className="count" id="word-count">{t("home.count", { n: words })}</span>
          </div>
          {!busy && <p className="gate" role="status">{gate}</p>}
          <div className="editor-foot">
            {band(mode)}
            <button type="submit" className="btn btn-primary" disabled={busy || reading || !token || words < minimum || words > maximum}>
              {t(busy ? "home.checking" : "home.check")}<Icon name="arrow" /></button>
          </div>
          {quota?.owner && <label className="save-choice"><input type="checkbox" checked={saveText} disabled={busy}
            onChange={(e) => setSaveText(e.target.checked)} />{t("account.save")}</label>}
          {words >= minimum && words <= maximum && <Verification key={mode + challenge} mode={mode} onToken={setToken} />}
          {error && <p role="alert" className="notice">{error === "too_short" ? t("errors.too_short", { n: minimum }) : t(`errors.${error}`, { n: maximum })}</p>}
        </form>
        {busy && <StatusBox stage={stage} />}
        <p className="privacy"><Icon name="lock" />{t("home.privacy")}</p>
        {saved && <div className="device-controls"><p>{savedNote}</p>{forgetButton}</div>}
      </div>
      <SampleCard mode={mode} />
    </div>
    <DoorSteps />
  </>;

  const progress = <>
    <section className="result-top progress" aria-labelledby="progress-title">
      <div className="result-copy">
        <div className="mode-row"><span className="mode-chip"><Icon name="layers" />{t("result.deepChip")}</span></div>
        <h1 id="progress-title" ref={progressTitle} tabIndex={-1}>{t("heat.reading")}</h1>
        <StatusBox stage={stage} />
      </div>
    </section>
    <HouseRule className="result-rule" />
  </>;

  const view = busy && mode === "deep" ? progress : !result || !saved ? home : <>
    <ResultHero result={result} mode={resultMode} at={saved.createdAt} id={saved.checkId} titleRef={resultTitle} issue
      top={fresh ? <StatusBox done /> : null} onPanel={openPanel}
      actions={<button type="button" className="btn btn-quiet" onClick={() => edit()}><Icon name="pen" />{t("home.again")}</button>} />
    <HouseRule className="result-rule" />
    <Flags result={result} />
  </>;

  const kit = result && saved && <KitSection note={savedNote}>
    <EvidenceKit result={result} mode={resultMode} version={saved.engineVersion} date={saved.createdAt} />
    {forgetButton}
  </KitSection>;

  return <MotionConfig reducedMotion="user">
    <div data-mode={result ? resultMode : mode}>
      <a className="skip" href="#main">{t("chrome.jump")}</a>
      <Masthead />
      <main id="main" tabIndex={-1} className="wrap">
        {view}
        {((busy && mode === "deep") || result?.sentences?.length) ? <SentenceHeatmap key={attempt} text={text}
          sentences={result?.sentences ?? sentences} streaming={busy} /> : null}
        {result && saved && (resultMode === "deep" ? <>
          <LensPanel result={result} mode="deep" />
          <Signals result={result} />
          {kit}
        </> : <>
          <Signals result={result} />
          <LensPanel result={result} mode="quick" onDeep={() => edit("deep")} />
          <Upsell at={saved.createdAt} onDeep={() => edit("deep")} />
          {kit}
        </>)}
      </main>
      <SiteFooter quota={result && quota ? <>{band(resultMode)}<small>{t("home.quotaNote")}</small></> : undefined}>
        <button type="button" className="link-button" onClick={() => openPanel("how")}>{t("chrome.how")}</button>
      </SiteFooter>
      <InfoDialog panel={panel} dialog={dialog} />
    </div>
  </MotionConfig>;
}
