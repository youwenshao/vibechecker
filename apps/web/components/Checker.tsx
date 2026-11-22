"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { MotionConfig } from "motion/react";
import { useLocale, useTranslations } from "next-intl";
import { readEssay, wordCount } from "../lib/essay";
import type { Mode } from "@vibechecker/contracts";
import { SentenceHeatmap, type DisplaySentence } from "./SentenceHeatmap";
import { StatusTicker } from "./StatusTicker";
import { CheckError, checkEssay, type Stage } from "../lib/check-stream";
import { deviceTtl, latestCheck, forgetChecks, saveCheck, type DeviceCheck } from "../lib/device";
import { LensPanel } from "./LensPanel";
import { CautionText } from "./CautionText";
import { EvidenceKit } from "./EvidenceKit";
import { Dial, Icon } from "./Icons";
import { Signals, VerdictGauge } from "./Instruments";
import { Verification } from "./Verification";

type Panel = "how" | "why" | "wrong";
type Quota = { owner: string | null; usage: Record<Mode, number>; limits: Record<Mode, number> };

async function readQuota(): Promise<Quota | null> {
  const response = await fetch("/api/quota", {cache:"no-store"});
  return response.ok ? response.json() : null;
}
type ErrorKey = "too_short" | "too_long" | "not_english" | "quota" | "turnstile" | "busy" | "internal" | "file" | "auth_required";
const errors = new Set<ErrorKey>(["too_short", "too_long", "not_english", "quota", "turnstile", "busy", "internal", "file", "auth_required"]);

export function Checker() {
  const t = useTranslations();
  const locale = useLocale();
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
  const [panel, setPanel] = useState<Panel>("why");
  const progressTitle = useRef<HTMLHeadingElement>(null);
  const resultTitle = useRef<HTMLHeadingElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const touched = useRef(false);
  const words = wordCount(text);
  const result = editing ? undefined : saved?.result;

  useEffect(() => {
    let mounted = true;
    readQuota().catch(() => null).then(async current => {
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
      setSaved(check);
    } catch (e) {
      const code = e instanceof CheckError ? e.code as ErrorKey : "internal";
      setError(errors.has(code) ? code : "internal");
    } finally {
      readQuota().then(current => {
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
    setText("");
    setError(undefined);
    setStorageError(undefined);
    requestAnimationFrame(() => box.current?.focus());
  }

  function edit() {
    setEditing(true);
    requestAnimationFrame(() => box.current?.focus());
  }

  const panelTitle = panel === "how" ? t("chrome.how") : t(`result.${panel}`);
  return <MotionConfig reducedMotion="user">
    <a className="skip" href="#main">{t("chrome.jump")}</a>
    <header className="masthead"><div className="mast-inner">
      <a className="wordmark" href={locale === "en" ? "/" : "/zh-HK"} aria-label={t("chrome.home")}>
        <Dial />{t("chrome.brand")}<span className="wordmark-dot" aria-hidden="true">.</span>
      </a>
      <nav><a href={`/${locale}/history`}>{t("account.title")}</a><a className="method-link" href={`/${locale}/methodology`}>{t("chrome.methodology")}</a>
        <a href={locale === "en" ? "/zh-HK" : "/"} lang={locale === "en" ? "zh-HK" : "en"}><Icon name="globe" />{t("chrome.locale")}</a></nav>
    </div></header>
    <main id="main" tabIndex={-1}>
      {busy && mode === "deep" ? <section className="report deep-progress">
        <span className="mode">{t("home.deep")}</span><h1 ref={progressTitle} tabIndex={-1}>{t("heat.reading")}</h1>
        <StatusTicker stage={stage}/>
        <p className="caution">{t("chrome.foot")}</p>
      </section> : !result ? <section className="home">
        <div className="hero">
          <h1>{t.rich("home.title", { br: () => <br />, dial: (letter) => <span className="dial-letter"><span className="sr-only">{letter}</span><Dial glyph /></span> })}</h1>
          <p>{t("home.subline")}</p>
        </div>
        <form className="editor" onSubmit={submit}>
          <div className="editor-heading"><label htmlFor="essay">{t("home.label")}</label>
            <fieldset className="mode-picker" disabled={busy || reading}>
              <legend className="sr-only">{t("home.mode")}</legend>
              {(["quick", "deep"] as const).map((choice) => <label key={choice}>
                <input type="radio" name="mode" value={choice} checked={mode === choice} onChange={() => {
                  touched.current = true; setMode(choice); setToken(""); setError(undefined);
                }}/><span>{t(`home.${choice}`)}</span>
              </label>)}
            </fieldset></div>
          <div className="writing-area">
            <textarea ref={box} id="essay" value={text} onChange={(event) => {
              touched.current = true; setText(event.target.value); setError(undefined);
            }} disabled={busy || reading} placeholder={t("home.placeholder")} aria-describedby="word-limits word-count" dir="auto"/>
            <div className="writing-tools">
              <input ref={file} type="file" accept=".txt,.md,.docx" className="file-input" tabIndex={-1} aria-label={t("home.fileHelp")}
                onChange={(event) => void loadFile(event.target.files?.[0])}/>
              <button type="button" className="upload" disabled={busy || reading} onClick={() => file.current?.click()} title={t("home.fileHelp")}><Icon name="attach"/>{t("home.upload")}</button>
              <span id="word-count">{t("home.count", { n: words })}</span>
            </div>
          </div>
          <div className="submit-row">
            <div><p id="word-limits">{t(mode === "deep" ? "home.deepLimits" : "home.limits", { n: minimum })}</p>
              {busy ? <StatusTicker stage={stage}/> : <p className="status" role="status">{words > maximum ? t("errors.too_long", { n: maximum }) : words > 0 && words < minimum ? t(mode === "quick" ? "home.more" : "home.moreDeep", { n: minimum - words })
                : words >= minimum ? t(token ? (mode === "quick" ? "home.ready" : "home.readyDeep") : "home.verification") : null}</p>}</div>
            <button type="submit" className="primary" disabled={busy || reading || !token || words < minimum || words > maximum}>{t(busy ? "home.checking" : "home.check")}<Icon name="arrow"/></button>
          </div>
          {quota && <div className="quota-meter"><meter min={0} max={quota.limits[mode]} value={Math.max(0,quota.limits[mode]-quota.usage[mode])} aria-label={t("home."+mode)}/>
            <span>{t("account.quota",{mode:t("home."+mode),left:Math.max(0,quota.limits[mode]-quota.usage[mode]),limit:quota.limits[mode]})}</span></div>}
          {quota?.owner && <label className="save-choice"><input type="checkbox" checked={saveText} disabled={busy} onChange={e=>setSaveText(e.target.checked)}/>{t("account.save")}</label>}
          {words >= minimum && words <= maximum && <Verification key={mode + challenge} mode={mode} onToken={setToken} />}
          {error && <p role="alert" className="notice">{error === "too_short" ? t("errors.too_short", { n: minimum }) : t(`errors.${error}`, { n: maximum })}</p>}
        </form>
        <p className="privacy"><Icon name="lock"/>{t("home.privacy")}</p>
      </section> : <div className="report">
        <div className="report-header"><span className="mode"><Icon name="bolt"/>{t(`home.${saved?.mode ?? "quick"}`)}</span>
          <button className="text-button" onClick={edit}><Icon name="pencil"/>{t("home.again")}</button></div>
        <section className="verdict"><div>
          <h1 ref={resultTitle} tabIndex={-1}>{t("result.title")}</h1>
          <h2>{t(`result.bands.${result.band}`)}</h2>
          <p>{t(`result.interpretation.${result.band}`)}</p>
          <div className="actions">
            {(["why", "wrong"] as const).map((name) => <button className="pill" key={name} onClick={() => openPanel(name)}>{t(`result.${name}`)}<Icon name="arrow"/></button>)}
          </div>
        </div><VerdictGauge result={result}/></section>
        <aside className="caution"><Icon name="bolt"/><p><CautionText/></p></aside>
        {result.flags.length > 0 && <section className="flags"><h2>{t("result.flags")}</h2>
          <ul>{result.flags.map((flag) => <li key={flag}>{t(`result.${flag}`)}</li>)}</ul></section>}
      </div>}
      {((busy && mode === "deep") || result?.sentences?.length) ? <div className="report heat-report">
        <SentenceHeatmap key={attempt} text={text} sentences={result?.sentences ?? sentences} streaming={busy}/>
      </div> : null}
      {result && saved && <div className="report signals-report"><Signals result={result}/><LensPanel result={result}/>
        <EvidenceKit result={result} mode={saved.mode??"quick"} version={saved.engineVersion} date={saved.createdAt}/></div>}
      {saved && <div className="device-controls">
        <p>{storageError ? t(`home.${storageError}`) : t("result.saved")}</p>
        <button type="button" className="text-button" disabled={busy || reading} onClick={() => void forget()}><Icon name="erase"/>{t("home.forget")}</button>
      </div>}
    </main>
    <footer><span className="footer-brand">{t("chrome.brand")}.</span>{!result && !busy && <p>{t("chrome.foot")}</p>}
      <a href={`/${locale}/privacy`}>{t("policy.privacy")}</a><a href={`/${locale}/terms`}>{t("policy.terms")}</a>
      <button className="text-button" onClick={() => openPanel("how")}>{t("chrome.how")}</button></footer>
    <dialog ref={dialog} aria-labelledby="panel-title">
      <div className="dialog-head"><h2 id="panel-title">{panelTitle}</h2>
        <button className="circle-button" onClick={() => dialog.current?.close()} aria-label={t("chrome.close")}><Icon name="close"/></button></div>
      <p>{panel === "how" ? t("home.howBody") : t(`result.${panel}Body`)}</p>
      <a className="text-button" href={`/${locale}/methodology`}>{t("chrome.methodology")}<Icon name="arrow"/></a>
    </dialog>
  </MotionConfig>;
}
