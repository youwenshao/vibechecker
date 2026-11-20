import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const essay = "A short example sentence with an observation about the library. ".repeat(18).trim();

test("a normalized re-check receives its own claim and the cached score", async ({ request }) => {
  const text = "A café by the harbour.\r\n" + essay;
  async function submit(submitted: string) {
    const response = await request.post("/api/checks", {
      data: {text: submitted, mode: "quick", turnstileToken: "browser-test-token"},
    });
    expect(response.ok()).toBe(true);
    return (await response.text()).trim().split("\n").map(line => JSON.parse(line));
  }
  const first = (await submit(text)).at(-1);
  expect(first.type).toBe("result");
  await expect.poll(async () => (await (await request.get(
    "http://127.0.0.1:4328/stored?id=" + first.checkId
  )).json())?.p_id).toBe(first.checkId);
  const second = await submit(text.replace("\r\n", "\n").normalize("NFD"));
  expect(second.map(event => event.type)).toEqual(["result"]);
  expect(second[0].result).toEqual(first.result);
  expect(second[0].checkId).not.toBe(first.checkId);
  expect(second[0].claimToken).not.toBe(first.claimToken);
});
test.beforeEach(async ({ page }) => {
  await page.route("https://challenges.cloudflare.com/turnstile/v0/api.js**", (route) => route.fulfill({
    contentType: "application/javascript",
    body: `window.turnstile = {
      render(container, options) { options.callback("browser-test-token"); return "test"; },
      remove() {}
    };`,
  }));
});

test("word gate, keyboard disclosure, streamed result and device erasure", async ({ page }) => {
  await page.goto("/");
  const box = page.getByRole("textbox", { name: "Your essay" });
  const check = page.getByRole("button", { name: "Check my essay" });
  await box.fill("Still drafting.");
  await expect(check).toBeDisabled();
  await expect(page.getByText("148 more words for a Quick check.")).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await box.fill(essay);
  await check.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Robot-smell index" })).toBeVisible();
  await expect(page.getByText("Likely range 48–75")).toBeVisible();
  await expect(page.getByText("Mixed signals", { exact: true })).toBeVisible();
  await expect(page.getByText("A detector score is a reason to look closer, never proof.", { exact: true })).toBeVisible();
  for (const name of ["Why this score?", "Why can detectors be wrong?"]) {
    const trigger = page.getByRole("button", { name, exact: true });
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog", { name })).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
  }
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Robot-smell index" })).toBeVisible();
  await page.getByRole("button", { name: "Forget on this device" }).click();
  await expect(box).toBeEmpty();
  await page.reload();
  await expect(box).toBeEmpty();
  await expect(page.getByRole("heading", { name: "Robot-smell index" })).toHaveCount(0);
});

test("reduced motion and text-file import", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.locator('input[type=file]').setInputFiles({ name: "draft.md", mimeType: "text/markdown", buffer: Buffer.from(essay) });
  await expect(page.getByRole("textbox")).toHaveValue(essay);
  await page.getByRole("button", { name: "Check my essay" }).click();
  await expect(page.getByText("Likely range 48–75")).toBeVisible();
  await expect(page.getByTestId("gauge-value")).toHaveText("62");
  expect(await page.getByTestId("gauge-value").evaluate((node) => node.getAnimations().length)).toBe(0);
});

test("returns an actionable language refusal and retains the draft", async ({ page }) => {
  await page.goto("/");
  const text = "Bonjour les amis du quartier. ".repeat(32).trim();
  await page.getByRole("textbox").fill(text);
  await page.getByRole("button", { name: "Check my essay" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "English essays" })).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveValue(text);
  await expect(page.getByRole("button", { name: "Check my essay" })).toBeEnabled();
});

test("imports a Word document into the editor on the device", async ({ page }) => {
  await page.goto("/");
  await page.locator("input[type=file]").setInputFiles("e2e/fixtures/essay.docx");
  await expect(page.getByRole("textbox")).toHaveValue(/Today I walked to the library before class\./);
  await expect(page.getByText("8 words", { exact: true })).toBeVisible();
});

test("drops expired essay and claim records on the next visit", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-20T00:00:00Z"));
  await page.goto("/");
  await page.getByRole("textbox").fill(essay);
  await page.getByRole("button", { name: "Check my essay" }).click();
  await expect(page.getByText("Likely range 48–75")).toBeVisible();
  await page.clock.setFixedTime(new Date("2026-12-21T00:00:00Z"));
  await page.reload();
  await expect(page.getByRole("textbox")).toBeEmpty();
  await expect.poll(async () => page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve) => {
      const req = indexedDB.open("vibechecker", 1);
      req.onsuccess = () => resolve(req.result);
    });
    const count = await new Promise<number>((resolve) => {
      const req = db.transaction("checks").objectStore("checks").count();
      req.onsuccess = () => resolve(req.result);
    });
    db.close();
    return count;
  })).toBe(0);
});

test("renders Traditional Chinese on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/zh-HK");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-HK");
  await expect(page.getByRole("textbox", { name: "你的文章" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("retries a broken primary stream once and persists the fallback result without text", async ({ page, request }) => {
  const bodies: string[] = [];
  page.on("request", (req) => {
    if (new URL(req.url()).pathname === "/api/checks" && req.postData()) bodies.push(req.postData()!);
  });
  await page.goto("/");
  const text = "Failover " + essay;
  await page.getByRole("textbox").fill(text);
  await page.getByRole("button", { name: "Check my essay" }).click();
  await expect(page.getByText("Likely range 48–75")).toBeVisible();
  expect(bodies).toHaveLength(2);
  expect(JSON.parse(bodies[1]).retryToken).toBeTruthy();
  const stored = await page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve) => {
      const req = indexedDB.open("vibechecker", 1);
      req.onsuccess = () => resolve(req.result);
    });
    const saved = await new Promise<{ checkId: string; claimToken: string; text: string }>((resolve) => {
      const req = db.transaction("checks").objectStore("checks").getAll();
      req.onsuccess = () => resolve(req.result[0]);
    });
    db.close();
    return saved;
  });
  expect(stored.text).toBe(text);
  expect(stored.claimToken).toBeTruthy();
  await expect.poll(async () => {
    const response = await request.get("http://127.0.0.1:4328/stored?id=" + stored.checkId);
    const row = await response.json();
    if (!row) return null;
    expect(JSON.stringify(row)).not.toContain(text);
    expect(JSON.stringify(row)).not.toContain(stored.claimToken);
    return row.p_backend;
  }).toBe("mlx-cuda");
});
