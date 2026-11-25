"use client";
import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Icon } from "./Icons";
import { StampedMark } from "./Marks";

export function Wordmark({ href, label }: { href?: string; label?: string }) {
  const t = useTranslations("chrome");
  const body = <>{t("brand")}<span className="dot"><StampedMark /></span></>;
  return href ? <a className="wordmark" href={href} aria-label={label}>{body}</a> : <span className="wordmark">{body}</span>;
}

export function GoogleNotice() {
  const t = useTranslations("home");
  return <p className="google-notice">{t.rich("googleNotice", {
    link: (chunks) => <a href={t("privacyUrl")}>{chunks}</a>,
  })}</p>;
}

export function Masthead({ current }: { current?: "history" | "methodology" }) {
  const t = useTranslations("chrome");
  const locale = useLocale();
  const other = locale === "en" ? "zh-HK" : "en";
  const path = usePathname() ?? "";
  const switched = /^\/(en|zh-HK)(?=\/|$)/.test(path) ? path.replace(/^\/(en|zh-HK)/, "/" + other) : "/" + other;
  const here = (page: typeof current) => (page === current ? "page" : undefined);
  return <header className="site-head wrap">
    <Wordmark href={"/" + locale} label={t("home")} />
    <nav className="nav" aria-label={t("nav")}>
      <a href={`/${locale}/history`} aria-current={here("history")}><Icon name="clock" />{t("history")}</a>
      <a href={`/${locale}/methodology`} aria-current={here("methodology")}><Icon name="book" />{t("methodology")}</a>
      <a href={switched} lang={other} hrefLang={other}><Icon name="globe" />{t("locale")}</a>
    </nav>
    <span className="beta"><span className="dot"><StampedMark /></span>{t("beta")}</span>
  </header>;
}

export function SiteFooter({ quota, children }: { quota?: ReactNode; children?: ReactNode }) {
  const t = useTranslations();
  const locale = useLocale();
  return <footer className="site-foot">
    {quota && <div className="wrap foot-grid"><div className="foot-quota">{quota}</div></div>}
    <div className="wrap foot-base">
      <Wordmark />
      <p>{t("chrome.foot")}</p>
      <nav className="foot-nav" aria-label={t("chrome.footer")}>
        <a href={`/${locale}/privacy`}>{t("policy.privacy")}</a>
        <a href={`/${locale}/terms`}>{t("policy.terms")}</a>
        {children}
      </nav>
    </div>
  </footer>;
}
