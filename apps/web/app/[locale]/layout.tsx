import type { ReactNode } from "react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { routing } from "../../i18n/routing";
import "../globals.css";

type Props = { params: Promise<{ locale: string }> };

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  const t = await getTranslations({ locale, namespace: "home" });
  return {
    applicationName: "VibeChecker",
    title: t("pageTitle"),
    description: t("subline"),
    openGraph: { siteName: "VibeChecker", title: t("pageTitle"), description: t("subline") },
    icons: {
      icon: [
        { url: "/icon.svg", type: "image/svg+xml", sizes: "any" },
        { url: "/icon.png", type: "image/png", sizes: "512x512" },
        {
          url: "/brand/icon-night-cream.png",
          type: "image/png",
          sizes: "1024x1024",
          media: "(prefers-color-scheme: dark)",
        },
      ],
      apple: [{ url: "/apple-icon.png", sizes: "180x180", type: "image/png" }],
    },
  };
}

export default async function Layout({ children, params }: Props & { children: ReactNode }) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  return <html lang={locale}><body><NextIntlClientProvider>{children}</NextIntlClientProvider></body></html>;
}
