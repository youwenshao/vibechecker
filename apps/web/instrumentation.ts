import type { Instrumentation } from "next";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs" && process.env.SENTRY_DSN) {
    const Sentry = await import("@sentry/nextjs");
    const { privacyOptions } = await import("./lib/telemetry");
    Sentry.init({ ...privacyOptions, dsn: process.env.SENTRY_DSN, defaultIntegrations: false });
  }
}
export const onRequestError: Instrumentation.onRequestError = async (error) => {
  if (process.env.SENTRY_DSN) (await import("@sentry/nextjs")).captureException(error);
};
