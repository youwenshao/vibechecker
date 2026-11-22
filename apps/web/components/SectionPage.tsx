import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";
import { Masthead, SiteFooter } from "./Chrome";

export async function SectionPage({
  locale,
  current,
  className,
  children,
}: {
  locale: string;
  current?: "history" | "methodology";
  className?: string;
  children: ReactNode;
}) {
  const t = await getTranslations({ locale });
  return (
    <>
      <a className="skip" href="#main">{t("chrome.jump")}</a>
      <Masthead current={current} />
      <main id="main" tabIndex={-1} className={className ? "wrap " + className : "wrap"}>
        {children}
      </main>
      <SiteFooter />
    </>
  );
}
