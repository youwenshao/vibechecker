import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";

const essay = "My research notes explain how the harbour changed after the storm. ".repeat(31);
test.beforeEach(async ({ page }) => {
  await page.route("https://challenges.cloudflare.com/turnstile/v0/api.js**", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.turnstile={render(el,o){o.callback(o.action==="deep_check"?"browser-deep-token":o.action==="auth_check"?"auth-test-token":"browser-test-token");return "widget"},remove(){}}`,
    }),
  );
});
test("claims a device check, saves only by opt-in, and deletes the check, history and account", async ({
  page,
  request,
}) => {
  const meta = async () => (await page.request.get("/api/account")).json();
  async function check(save = false) {
    await page.goto("/en");
    await page.getByRole("textbox", { name: "Your essay" }).fill(essay);
    if (save) await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Check my essay" }).click();
    await expect(page.getByRole("heading", { name: "Robot vibes", exact: true })).toBeVisible();
    return page.evaluate(
      async () =>
        new Promise<string>((resolve) => {
          const db = indexedDB.open("vibechecker", 1);
          db.onsuccess = () => {
            const latest = db.result
              .transaction("checks")
              .objectStore("checks")
              .index("createdAt")
              .openCursor(null, "prev");
            latest.onsuccess = () => {
              resolve(latest.result!.value.checkId);
              db.result.close();
            };
          };
        }),
    );
  }
  const id = await check();
  await page.getByRole("link", { name: "History", exact: true }).click();
  const email = "phase2-" + Date.now() + "@example.test";
  await page.getByLabel("Email address").fill(email);
  const started = page.waitForResponse((r) => r.url().endsWith("/api/auth/start"));
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  expect((await started).status()).toBe(200);
  await expect(page.getByText(/Check your inbox/)).toBeVisible();
  const link = await (
    await request.get("http://127.0.0.1:4328/inbox?email=" + encodeURIComponent(email))
  ).json();
  await page.goto(link);
  await expect(page.getByRole("button", { name: "View result" })).toHaveCount(1);
  expect((await meta()).rows[0].id).toBe(id);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Delete check", exact: true }).click();
  await page.getByRole("button", { name: "Confirm deletion" }).click();
  await expect(page.getByText("Your saved results will appear here.")).toBeVisible();
  const newId = await check(true);
  const stored = await (await request.get("http://127.0.0.1:4328/stored?id=" + newId)).json();
  expect(stored.p_envelope.wrapped).toBeTruthy();
  expect(JSON.stringify(stored)).not.toContain("harbour");
  await page.getByRole("link", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: "View result" }).click();
  await page.getByText("Saved essay", { exact: true }).click();
  await expect(page.getByText(essay.trim(), { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Delete all checks" }).click();
  await page.getByRole("button", { name: "Confirm deletion" }).click();
  await expect(page.getByText("Your saved results will appear here.")).toBeVisible();
  await check(true);
  await page.getByRole("link", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: "Delete account", exact: true }).click();
  await page.getByRole("button", { name: "Confirm deletion" }).click();
  await expect(page.getByLabel("Email address")).toBeVisible();
  expect((await meta()).owner).toBeNull();
});
test("Google sign-in requires the auth challenge and returns to the selected locale", async ({
  page,
}) => {
  await page.goto("/zh-HK/history");
  const rejected = await page.request.post("/api/auth/start", {
    headers: { origin: "http://127.0.0.1:4327" },
    data: {
      locale: "zh-HK",
      provider: "google",
      token: "browser-test-token",
    },
  });
  expect(rejected.status()).toBe(403);
  await page.getByRole("button", { name: "以 Google 登入" }).click();
  await expect(page.getByRole("button", { name: "登出" })).toBeVisible();
  await expect(page).toHaveURL(/zh-HK\/history$/);
  await page.getByRole("button", { name: "登出" }).click();
  await expect(page.getByLabel("電郵地址")).toBeVisible();
});
test("switches the privacy and terms pages between Hong Kong Chinese and English", async ({
  page,
}) => {
  await page.goto("/zh-HK");
  await page.getByRole("link", { name: "私隱政策" }).click();
  await expect(page.getByRole("heading", { name: "服務供應商及跨境傳送" })).toBeVisible();
  await page.getByRole("link", { name: "English" }).click();
  await expect(
    page.getByRole("heading", { name: "Your choices under Hong Kong’s PDPO" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Terms of use" }).click();
  await expect(page.getByRole("heading", { name: "Research beta" })).toBeVisible();
});
for (const locale of ["en", "zh-HK"])
  test("downloads one-page evidence in " + locale, async ({ page }, info) => {
    await page.goto("/" + locale);
    await page.locator(".mode-picker label").nth(1).click();
    await page.getByRole("textbox").fill("Full kit. " + essay);
    await page.locator("button[type=submit]").click();
    const kit = page.getByRole("button", { name: /PDF/ });
    await expect(kit).toBeVisible();
    if (locale === "en") {
      const turnitin = page.locator(".lens-row").filter({ hasText: "Turnitin-style" });
      await turnitin.locator("summary").click();
      await expect(turnitin.getByText("*% (below 20%)", { exact: true })).toBeVisible();
      await expect(turnitin.getByText(/real Turnitin model is proprietary/)).toBeVisible();
    }
    const downloaded = page.waitForEvent("download");
    await kit.click();
    const file = info.outputPath("evidence.pdf");
    await (await downloaded).saveAs(file);
    const bytes = (await readFile(file)).toString("latin1");
    expect(bytes.startsWith("%PDF")).toBe(true);
    expect(bytes.match(/\/Type\s*\/Page\b/g)).toHaveLength(1);
  });
