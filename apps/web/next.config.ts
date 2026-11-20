import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

const config: NextConfig = {
  // The public Turnstile test key in the smoke build must never enter a deployable bundle.
  distDir: process.env.VIBE_E2E_BUILD === "1" ? ".next-e2e" : ".next",
  poweredByHeader: false,
  transpilePackages: ["@vibechecker/contracts"],
};

export default createNextIntlPlugin()(config);
