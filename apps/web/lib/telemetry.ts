import type { ErrorEvent } from "@sentry/nextjs";

// Build a new event from a closed vocabulary. Arbitrary errors, breadcrumbs,
// request URLs, cookies and component props can all contain submitted text.
export function scrubEvent(event: ErrorEvent): ErrorEvent {
  const kind = event.exception?.values?.[0]?.type;
  const category =
    kind && ["TypeError", "RangeError", "ReferenceError", "SyntaxError"].includes(kind)
      ? kind
      : "Error";
  const operation = event.tags?.operation;
  return {
    type: undefined,
    level: "error",
    message: "VibeChecker application error",
    event_id: event.event_id && /^[a-f0-9]{32}$/.test(event.event_id) ? event.event_id : undefined,
    tags: {
      category,
      ...(operation === "checks" || operation === "history" || operation === "sign-in"
        ? { operation }
        : {}),
    },
    platform: "javascript",
  };
}

export async function reportServiceFailure(operation: "checks" | "history" | "sign-in") {
  if (process.env.SENTRY_DSN) {
    const { captureMessage } = await import("@sentry/nextjs");
    captureMessage("Service request failed", { level: "error", tags: { operation } });
  }
}
export const privacyOptions = {
  sendDefaultPii: false,
  tracesSampleRate: 0,
  autoSessionTracking: false,
  maxBreadcrumbs: 0,
  enableLogs: false,
  sendClientReports: false,
  beforeSend: scrubEvent,
} as const;
