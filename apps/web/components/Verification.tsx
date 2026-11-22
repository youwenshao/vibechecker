"use client";
import type { Mode } from "@vibechecker/contracts";
import Script from "next/script";
import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";

type Turnstile = {
  render: (element: HTMLElement, options: Record<string, unknown>) => string;
  remove: (widget: string) => void;
};
declare global { interface Window { turnstile?: Turnstile } }

export function Verification({ mode, onToken }: { mode: Mode | "auth"; onToken: (token: string) => void }) {
  const root = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const sitekey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
  const t = useTranslations("home");
  const locale = useLocale();
  useEffect(() => {
    const api = window.turnstile;
    if (!ready || !root.current || !api || !sitekey) return;
    const widget = api.render(root.current, {
      sitekey, action: mode + "_check", theme: "light", appearance: "interaction-only",
      language: locale === "zh-HK" ? "zh-tw" : "en",
      callback: (token: string) => { setFailed(false); onToken(token); },
      "expired-callback": () => onToken(""),
      "error-callback": () => { setFailed(true); onToken(""); },
    });
    return () => { api.remove(widget); onToken(""); };
  }, [ready, sitekey, locale, onToken, mode]);
  return <>
    {sitekey && <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
      onReady={() => setReady(true)} onError={() => setFailed(true)} />}
    <div ref={root} />
    {(!sitekey || failed) && <p role="alert" className="status">{t("unavailable")}</p>}
  </>;
}
