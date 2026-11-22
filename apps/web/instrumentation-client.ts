import * as Sentry from "@sentry/nextjs";
import { privacyOptions } from "./lib/telemetry";

if (process.env.NEXT_PUBLIC_SENTRY_DSN)
  Sentry.init({
    ...privacyOptions,
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    integrations: () => [Sentry.globalHandlersIntegration()],
  });
