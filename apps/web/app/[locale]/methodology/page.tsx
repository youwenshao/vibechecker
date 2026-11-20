import { getTranslations, setRequestLocale } from "next-intl/server";
import { Dial, Icon } from "../../../components/Icons";
import { BaseRate } from "../../../components/BaseRate";
import deep from "../../../../../eval/reports/phase-1/report.json";
import quick from "../../../../../eval/reports/quick-m6-fp32-v0/report.json";

type Rate = { denominator: number; rate: number | null; wilson95: number[] | null };
type Report = {
  version: string; release_ready: boolean; skipped?: Record<string, number>; metrics: Record<string, { fpr_high: Rate }>;
  reliability_bins?: { mean_score: number | null; observed_fraction: number | null; count: number }[];
};
type Props = { params: Promise<{ locale: string }> };
const cohorts = ["pooled", "genre/essay", "fairness/ESL-essay", "dataset/liang/toefl", "writer/native_proxy"];

export async function generateMetadata({ params }: Props) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "method" });
  return { title: t("pageTitle"), description: t("intro") };
}

async function Evidence({ report, locale, mode }: { report: Report; locale: string; mode: "quick" | "deep" }) {
  const t = await getTranslations({ locale, namespace: "method" });
  const percent = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format;
  const groupNames = [t("all"), t("essay"), t("esl"), t("toefl"), t("native")];
  const excludedToefl = report.skipped?.["liang/toefl/length"] ?? 0;
  const bins = (report.reliability_bins ?? []).flatMap((bin) =>
    bin.count && bin.mean_score !== null && bin.observed_fraction !== null ? [{
      mean: bin.mean_score, observed: bin.observed_fraction, count: bin.count,
    }] : []);
  function table(keys: string[]) {
    return <div className="measure-table"><table>
      <caption className="sr-only">{t("fpr")}</caption>
      <thead><tr><th scope="col">{t("cohort")}</th><th scope="col">{t("humanCount")}</th>
        <th scope="col">{t("rate")}</th><th scope="col">{t("wilson")}</th></tr></thead>
      <tbody>{keys.map((key) => {
        const rate = report.metrics[key]?.fpr_high;
        const label = groupNames[cohorts.indexOf(key)] ?? key;
        return <tr key={key}><th scope="row">{label}</th>
          <td>{rate?.denominator ?? "—"}</td>
          <td>{rate?.rate != null ? <span className="rate-bar" style={{ backgroundSize: `${rate.rate * 100}% 3px` }}>
            {percent(rate.rate)}</span> : t("unmeasured")}</td>
          <td>{rate?.wilson95 ? rate.wilson95.map(percent).join("–") : "—"}</td>
        </tr>;
      })}</tbody></table></div>;
  }
  const otherGroups = Object.keys(report.metrics).filter((key) => !cohorts.includes(key));
  return <section className="report-evidence" aria-label={t(mode)}>
    <h2>{t(mode)}</h2><p className="report-version">{report.version} · {t(report.release_ready ? "passed" : "pending")}</p>
    {mode === "deep" && <section><h3>{t("reliability")}</h3><p>{t("reliabilityBody")}</p>
      {bins.length ? <figure>
        <svg viewBox="0 0 240 135" className="reliability-plot" role="img" aria-label={t("reliability")}>
          <path d="M30 10v100h190" fill="none" stroke="currentColor"/>
          <path d="M30 110 220 10" fill="none" stroke="var(--muted)" strokeDasharray="3 3"/>
          {bins.map((bin) => <circle key={bin.mean} cx={30 + 190 * bin.mean} cy={110 - 100 * bin.observed} r="3.5" fill="var(--ink)"/>)}
          <g fontSize="8" fill="currentColor"><text x="28" y="122">0</text><text x="203" y="122">100%</text>
            <text x="4" y="14">100%</text></g>
        </svg>
        <details><summary>{t("plotData")}</summary><table><thead><tr>
          <th>{t("mean")}</th><th>{t("observed")}</th><th>{t("documents")}</th></tr></thead>
          <tbody>{bins.map((bin) => <tr key={bin.mean}><td>{percent(bin.mean)}</td><td>{percent(bin.observed)}</td><td>{bin.count}</td></tr>)}</tbody>
        </table></details></figure> : <p className="notice">{t("noBins")}</p>}
    </section>}
    <section><h3>{t("fpr")}</h3><p>{t("fprBody")}</p>{table(cohorts)}
      {otherGroups.length > 0 && <details><summary>{t("otherGroups")}</summary>{table(otherGroups)}</details>}
      <p className="table-footnote">{t("cohortNote")}
        {excludedToefl > 0 && <> {t("toeflSkipped", { n: excludedToefl })}</>}
      </p>
    </section>
  </section>;
}

export default async function Methodology({ params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale });
  const home = "/" + locale;
  return <>
    <a className="skip" href="#method">{t("method.skip")}</a>
    <header className="masthead"><div className="mast-inner">
      <a className="wordmark" href={home} aria-label={t("chrome.home")}><Dial/>{t("chrome.brand")}<span className="wordmark-dot">.</span></a>
      <nav><a className="method-link" href={home}>{t("method.check")}</a><a href={locale === "en" ? "/zh-HK/methodology" : "/en/methodology"}
        lang={locale === "en" ? "zh-HK" : "en"}><Icon name="globe"/>{t("chrome.locale")}</a></nav>
    </div></header>
    <main id="method" className="method-page" tabIndex={-1}>
      <h1>{t("chrome.methodology")}</h1><p className="method-lead">{t("method.intro")}</p>
      <p className="caution">{t("chrome.foot")}</p>
      <Evidence report={deep} mode="deep" locale={locale}/>
      <details className="quick-evidence"><summary>{t("method.quick")}</summary><Evidence report={quick} mode="quick" locale={locale}/></details>
      <section className="base-rate"><h2>{t("method.priorTitle")}</h2><p>{t("method.priorBody", { prior: deep.prior * 100 })}</p><BaseRate/></section>
    </main>
    <footer><a className="footer-brand" href={home}>{t("chrome.brand")}.</a><a className="text-button" href={home}>{t("method.check")}<Icon name="arrow"/></a></footer>
  </>;
}
