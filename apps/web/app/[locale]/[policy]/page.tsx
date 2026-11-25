import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SectionPage } from "../../../components/SectionPage";

export function generateStaticParams() {
  return [{ policy: "privacy" }, { policy: "terms" }];
}
export async function generateMetadata({ params }: { params: Promise<{ locale: string; policy: string }> }) {
  const { locale, policy } = await params;
  if (policy !== "privacy" && policy !== "terms") notFound();
  const t = await getTranslations({ locale });
  return { title: `${t("policy." + policy)} · ${t("chrome.brand")}` };
}
export default async function Policy({
  params,
}: {
  params: Promise<{ locale: string; policy: string }>;
}) {
  const { locale, policy } = await params;
  if (policy !== "privacy" && policy !== "terms") notFound();
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "policy" });
  const sections =
    policy === "privacy" ? ["operator", "data", "purpose", "google", "transfers", "rights"] : ["use", "limits", "beta"];
  const more: Record<string, string[]> = { purpose: ["features"], google: ["googleLimits"] };
  return (
    <SectionPage locale={locale} className="method-page policy-page">
      <h1>{t(policy)}</h1>
      {sections.map((k) => (
        <section className="report-evidence" key={k}>
          <h2>{t(k + "Title")}</h2>
          <p>{t(k)}</p>
          {(more[k] ?? []).map((name) => <p key={name}>{t(name)}</p>)}
        </section>
      ))}
      <a className="mail" href="mailto:hello@vibechecker.io">hello@vibechecker.io</a>
    </SectionPage>
  );
}
