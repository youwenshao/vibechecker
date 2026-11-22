import { defineConfig } from "@playwright/test";

const mock = "http://127.0.0.1:4328";
const env = {
  VIBE_E2E_BUILD: "1",
  APP_ORIGIN: "http://127.0.0.1:4327",
  NEXT_TELEMETRY_DISABLED: "1",
  NEXT_PUBLIC_TURNSTILE_SITE_KEY: "1x00000000000000000000AA",
  TURNSTILE_SECRET: "local-test-only",
  TURNSTILE_HOSTNAMES: "127.0.0.1",
  TURNSTILE_VERIFY_URL: mock + "/siteverify",
  SUPABASE_URL: mock,
  SUPABASE_PUBLISHABLE_KEY: "local-publishable-test-key",
  ESSAY_KEK: Buffer.alloc(32,7).toString("base64"),
  SUPABASE_SERVICE_ROLE_KEY: "local-test-only",
  CHECKS_SECRET: "e2e-only-device-signing-secret-32-bytes",
  INFERENCE_HMAC_SECRET: "e2e-only-inference-signing-secret-32-bytes",
  ENGINE_VERSION: "e2e-quick",
  PRIMARY_INFERENCE_URL: mock,
  CF_ACCESS_CLIENT_ID: "mock-primary",
  CF_ACCESS_CLIENT_SECRET: "mock-primary-secret",
  FALLBACK_INFERENCE_URL: mock,
};
export default defineConfig({
  testDir: "./e2e", fullyParallel: true, forbidOnly: !!process.env.CI, retries: 0,
  use: { baseURL: "http://127.0.0.1:4327", browserName: "chromium" },
  webServer: [
    { command: "node e2e/mock.mjs", url: mock + "/health" },
    { command: "pnpm build && pnpm start -H 127.0.0.1 -p 4327", url: "http://127.0.0.1:4327", env, timeout: 180000 },
  ],
});
