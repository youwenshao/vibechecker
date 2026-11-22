import { getTranslations, setRequestLocale } from "next-intl/server";
import { SectionPage } from "../../../components/SectionPage";
import { History } from "../../../components/History";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = await getTranslations({ locale });
  return { title: `${t("account.title")} · ${t("chrome.brand")}`, description: t("account.intro") };
}

export default async function HistoryPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <SectionPage locale={locale} current="history">
      <History />
    </SectionPage>
  );
}
