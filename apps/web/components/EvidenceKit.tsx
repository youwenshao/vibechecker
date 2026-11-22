"use client";
import { useState, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { CheckResult, Mode } from "@vibechecker/contracts";
import { Icon } from "./Icons";

export function KitSection({ note, children }: { note?: string; children: ReactNode }) {
  const t = useTranslations("kit");
  return <section className="kit plate" aria-labelledby="kit-title">
    <div>
      <span className="eyebrow">{t("title")}</span>
      <h2 id="kit-title">{t("heading")}</h2>
      <p>{t("advice")}</p>
      {note && <p className="kit-note">{note}</p>}
    </div>
    <div className="kit-actions">{children}</div>
  </section>;
}

export function EvidenceKit({
  result,
  mode,
  version,
  date,
}: {
  result: CheckResult;
  mode: Mode;
  version?: string;
  date: number;
}) {
  const locale = useLocale();
  const t = useTranslations();
  const [state, setState] = useState<"idle" | "busy" | "failed">("idle");
  async function download() {
    setState("busy");
    try {
      const { createKit } = await import("./EvidencePdf");
      const blob = await createKit({
        locale,
        title: t("kit.title"),
        index: result.index,
        meta: [
          t("home." + mode),
          t("home.count", { n: result.wordCount }),
          t("kit.date", {
            date: new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(date),
          }),
        ].join(" · "),
        version: t("kit.model", { version: version ?? t("kit.unknown") }),
        score: t("result.title"),
        band: t("result.bands." + result.band),
        range: t("result.range", result.interval),
        caution: t("chrome.foot"),
        whyTitle: t("kit.summary"),
        why: t("kit.why") + " " + t("kit.limits"),
        signalsTitle: t("kit.signals"),
        signals: result.signals.map((s) => [
          t("result." + s.id + ".title"),
          s.value.toFixed(2) + " / " + s.humanReference.toFixed(2),
        ]),
        flags: result.flags.map((flag) => t("result." + flag)),
        flagsTitle: t("result.flags"),
        adviceTitle: t("kit.process"),
        advice: t("kit.advice"),
        footer: t("kit.footer"),
        method: t("kit.source"),
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "vibechecker-" + locale + ".pdf";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      setState("idle");
    } catch {
      setState("failed");
    }
  }
  return (
    <>
      <button type="button" className="btn btn-primary" disabled={state === "busy"} onClick={download}>
        <Icon name="download" />
        {t(state === "busy" ? "kit.busy" : "kit.download")}
      </button>
      {state === "failed" && <p role="alert">{t("kit.fail")}</p>}
    </>
  );
}
