import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SectionPage } from "../../../components/SectionPage";

export function generateStaticParams() {
  return [{ policy: "privacy" }, { policy: "terms" }];
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
    policy === "privacy" ? ["data", "purpose", "transfers", "rights"] : ["use", "limits", "beta"];
  return (
    <SectionPage locale={locale} path={policy}>
      <h1>{t(policy)}</h1>
      {sections.map((k) => (
        <section className="report-evidence" key={k}>
          <h2>{t(k + "Title")}</h2>
          <p>{t(k)}</p>
          {k === "purpose" && <p>{t("features")}</p>}
        </section>
      ))}
      <a href="mailto:hello@vibechecker.io">hello@vibechecker.io</a>
    </SectionPage>
  );
}
