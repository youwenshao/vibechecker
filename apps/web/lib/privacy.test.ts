import { expect, it, vi } from "vitest";
import { encryptEssay, decryptEssay } from "./server/envelope";
import { scrubEvent } from "./telemetry";

it("binds unique envelope keys to both the check and owner", () => {
  vi.stubEnv("ESSAY_KEK", Buffer.alloc(32, 3).toString("base64"));
  try {
    const text = "My unreleased essay 🔒",
      a = encryptEssay(text, "one", "alice"),
      b = encryptEssay(text, "one", "alice");
    expect(a.wrapped).not.toEqual(b.wrapped);
    expect(JSON.stringify(a)).not.toContain(text);
    expect(decryptEssay(a, "one", "alice")).toBe(text);
    expect(() => decryptEssay(a, "two", "alice")).toThrow();
    expect(() => decryptEssay(a, "one", "bob")).toThrow();
    expect(() => decryptEssay({ ...a, wrapped: b.wrapped }, "one", "alice")).toThrow();
  } finally {
    vi.unstubAllEnvs();
  }
});
it("drops essay text from every Sentry event field", () => {
  const secret = "essay or OAuth credential";
  const clean = scrubEvent({
    type: undefined,
    message: secret,
    request: { data: secret, url: secret },
    extra: { secret },
    user: { email: secret },
    breadcrumbs: [{ message: secret }],
    exception: { values: [{ type: "TypeError", value: secret }] },
  });
  expect(clean.tags).toEqual({ category: "TypeError" });
  expect(JSON.stringify(clean)).not.toContain(secret);
});
