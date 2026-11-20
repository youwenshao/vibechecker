"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { MotionConfig, useReducedMotion } from "motion/react";
import { useLocale, useTranslations } from "next-intl";
import { readEssay, wordCount } from "../lib/essay";
import { CheckError, checkEssay } from "../lib/check-stream";
import { deviceTtl, forgetChecks, latestCheck, saveCheck, type DeviceCheck } from "../lib/device";
import { Dial, Icon, Signals, VerdictGauge } from "./Instruments";
import { Verification } from "./Verification";

type Panel = "how" | "why" | "wrong";
type ErrorKey = "too_short" | "too_long" | "not_english" | "quota" | "turnstile" | "busy" | "internal" | "file";
const errors = new Set<ErrorKey>(["too_short", "too_long", "not_english", "quota", "turnstile", "busy", "internal", "file"]);

export function Checker() {
  const t = useTranslations();
  const locale = useLocale();
  const [text, setText] = useState("");
  const [token, setToken] = useState("");
  const [challenge, setChallenge] = useState(0);
  const [error, setError] = useState<ErrorKey>();
  const [storageError, setStorageError] = useState<"storageError" | "forgetError">();
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [stage, setStage] = useState<"loading" | "scoring" | "fallback">("loading");
  const [saved, setSaved] = useState<DeviceCheck>();
  const [editing, setEditing] = useState(false);
  const [panel, setPanel] = useState<Panel>("how");
  const resultTitle = useRef<HTMLHeadingElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const touched = useRef(false);
  const reduce = useReducedMotion();
  const words = wordCount(text);
  const result = editing ? undefined : saved?.result;

  useEffect(() => {
    let mounted = true;
    latestCheck().then((check) => {
      if (mounted && !touched.current && check) {
        setSaved(check);
        setText(check.text);
      }
    }).catch(() => {});
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    if (result && touched.current) resultTitle.current?.focus();
  }, [result]);

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
    if (busy || reading || !token || words < 150 || words > 5000) return;
    touched.current = true;
    setBusy(true);
    setError(undefined);
    setStorageError(undefined);
    setStage("loading");
    try {
      const receipt = await checkEssay(text, token, setStage);
      const now = Date.now();
      const check = { ...receipt, text, createdAt: now, expiresAt: now + deviceTtl };
      try { await saveCheck(check); } catch { setStorageError("storageError"); }
      setEditing(false);
      setSaved(check);
    } catch (e) {
      const code = e instanceof CheckError ? e.code as ErrorKey : "internal";
      setError(errors.has(code) ? code : "internal");
    } finally {
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
      <nav><button type="button" onClick={() => openPanel("how")}>{t("chrome.how")}</button>
        <a href={locale === "en" ? "/zh-HK" : "/"} lang={locale === "en" ? "zh-HK" : "en"}><Icon name="globe" />{t("chrome.locale")}</a></nav>
    </div></header>
    <main id="main" tabIndex={-1}>
      {!result ? <section className="home">
        <div className="hero">
          <h1>{t.rich("home.title", { br: () => <br />, dial: (letter) => <span className="dial-letter"><span className="sr-only">{letter}</span><Dial glyph /></span> })}</h1>
          <p>{t("home.subline")}</p>
        </div>
        <form className="editor" onSubmit={submit}>
          <div className="editor-heading"><label htmlFor="essay">{t("home.label")}</label>
            <span className="mode"><Icon name="bolt" />{t("home.quick")}</span></div>
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
            <div><p id="word-limits">{t("home.limits")}</p>
              <p className="status" role="status">{busy ? t(`home.${reduce ? "loading" : stage}`)
                : words > 5000 ? t("errors.too_long") : words > 0 && words < 150 ? t("home.more", { n: 150 - words })
                : words >= 150 ? t(token ? "home.ready" : "home.verification") : null}</p></div>
            <button type="submit" className="primary" disabled={busy || reading || !token || words < 150 || words > 5000}>{t(busy ? "home.checking" : "home.check")}<Icon name="arrow"/></button>
          </div>
          {words >= 150 && <Verification key={challenge} onToken={setToken} />}
          {error && <p role="alert" className="notice">{t(`errors.${error}`)}</p>}
        </form>
        <p className="privacy"><Icon name="lock"/>{t("home.privacy")}</p>
      </section> : <div className="report">
        <div className="report-header"><span className="mode"><Icon name="bolt"/>{t("home.quick")}</span>
          <button className="text-button" onClick={edit}><Icon name="pencil"/>{t("home.again")}</button></div>
        <section className="verdict"><div>
          <h1 ref={resultTitle} tabIndex={-1}>{t("result.title")}</h1>
          <h2>{t(`result.bands.${result.band}`)}</h2>
          <p>{t(`result.interpretation.${result.band}`)}</p>
          <div className="actions">
            {(["why", "wrong"] as const).map((name) => <button className="pill" key={name} onClick={() => openPanel(name)}>{t(`result.${name}`)}<Icon name="arrow"/></button>)}
          </div>
        </div><VerdictGauge result={result}/></section>
        <aside className="caution"><Icon name="bolt"/><p>{t("chrome.foot")}</p></aside>
        {result.flags.length > 0 && <section className="flags"><h2>{t("result.flags")}</h2>
          <ul>{result.flags.map((flag) => <li key={flag}>{t(`result.${flag}`)}</li>)}</ul></section>}
        <Signals result={result} />
      </div>}
      {saved && <div className="device-controls">
        <p>{storageError ? t(`home.${storageError}`) : t("result.saved")}</p>
        <button type="button" className="text-button" disabled={busy || reading} onClick={() => void forget()}><Icon name="erase"/>{t("home.forget")}</button>
      </div>}
    </main>
    <footer><span className="footer-brand">{t("chrome.brand")}.</span>{!result && <p>{t("chrome.foot")}</p>}</footer>
    <dialog ref={dialog} aria-labelledby="panel-title">
      <div className="dialog-head"><h2 id="panel-title">{panelTitle}</h2>
        <button className="circle-button" onClick={() => dialog.current?.close()} aria-label={t("chrome.close")}><Icon name="close"/></button></div>
      <p>{panel === "how" ? t("home.howBody") : t(`result.${panel}Body`)}</p>
    </dialog>
  </MotionConfig>;
}
