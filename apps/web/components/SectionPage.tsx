import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";
import { Dial, Icon } from "./Icons";

export async function SectionPage({
  locale,
  path,
  children,
}: {
  locale: string;
  path: string;
  children: ReactNode;
}) {
  const t = await getTranslations({ locale });
  const other = locale === "en" ? "zh-HK" : "en";
  return (
    <>
      <header className="masthead">
        <div className="mast-inner">
          <a className="wordmark" href={"/" + locale}>
            <Dial />
            {t("chrome.brand")}.
          </a>
          <nav>
            <a href={"/" + locale}>{t("method.check")}</a>
            <a href={"/" + other + "/" + path} lang={other}>
              <Icon name="globe" />
              {t("chrome.locale")}
            </a>
          </nav>
        </div>
      </header>
      <main className="method-page account-page">{children}</main>
      <footer>
        <a href={"/" + locale + "/privacy"}>{t("policy.privacy")}</a>
        <a href={"/" + locale + "/terms"}>{t("policy.terms")}</a>
      </footer>
    </>
  );
}
