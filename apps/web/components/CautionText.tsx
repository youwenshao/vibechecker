import { useLocale, useTranslations } from "next-intl";
import english from "../messages/en.json";

export function CautionText() {
  const t = useTranslations("chrome");
  const locale = useLocale();
  return (
    <>
      {t("foot")}
      {locale !== "en" && (
        <small className="original-caution" lang="en">
          {english.chrome.foot}
        </small>
      )}
    </>
  );
}
