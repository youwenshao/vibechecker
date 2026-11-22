import { setRequestLocale } from "next-intl/server";
import { SectionPage } from "../../../components/SectionPage";
import { History } from "../../../components/History";

export default async function HistoryPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <SectionPage locale={locale} path="history">
      <History />
    </SectionPage>
  );
}
