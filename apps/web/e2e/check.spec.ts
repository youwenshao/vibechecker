import { readFileSync } from "node:fs";
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
      render(container, options) { options.callback(options.action === "deep_check" ? "browser-deep-token" : "browser-test-token"); return "test"; },
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

const deepEssay = "The library opened early and the lamps were already on. ".repeat(32).trim();

test("Deep streams a Unicode sentence, supports keyboard inspection and restores its local map", async ({ page, request }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("radio", { name: "Deep check" }).check();
  const box = page.getByRole("textbox");
  const submit = page.getByRole("button", { name: "Check my essay" });
  await box.fill("A short draft");
  await expect(submit).toBeDisabled();
  await expect(page.getByText("297 more words for a Deep check.")).toBeVisible();
  await box.fill("word ".repeat(2501));
  await expect(submit).toBeDisabled();
  await expect(page.getByText(/up to 2,500 words/)).toBeVisible();
  const first = "Stream demo 😀 at the café.";
  await box.fill(first + "\n\n" + deepEssay);
  await submit.click();
  const map = page.getByRole("region", { name: "Sentence heatmap" });
  const marker = map.locator(".sentence-marker").first();
  await expect(marker).toHaveText(first);
  await expect(map.getByText("1 sentence read so far")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Robot-smell index" })).toHaveCount(0);
  expect(await marker.evaluate((el) => el.getAnimations().length)).toBe(0);
  await marker.focus();
  await expect(map.getByRole("tooltip")).toContainText("Word likelihood gap");
  await request.get("http://127.0.0.1:4328/continue-heatmap");
  await expect(page.getByText("Likely range 48–75")).toBeVisible();
  await expect(map.locator(".sentence-marker")).toHaveCount(33);
  await marker.focus();
  await page.keyboard.press("ArrowRight");
  await expect(map.locator(".sentence-marker").nth(1)).toBeFocused();
  await expect(map.getByRole("tooltip")).toContainText("Model agreement");
  await page.keyboard.press("Escape");
  await expect(map.getByRole("tooltip")).toHaveCount(0);
  await map.getByRole("combobox", { name: "Highlight by signal" }).selectOption("e4");
  await expect(map.locator(".sentence-marker")).toHaveCount(16);
  await map.getByRole("button", { name: "List", exact: true }).click();
  await expect(map.locator(".sentence-list li")).toHaveCount(16);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.reload();
  await expect(map.locator(".sentence-marker")).toHaveCount(33);
  await expect(marker).toHaveText(first);
});

test("Deep cache and retry keep sentence offsets tied to the exact submitted text", async ({ request }) => {
  async function post(text: string, mode = "deep", retryToken?: string) {
    const r = await request.post("/api/checks", { data: { mode, text, retryToken,
      turnstileToken: mode === "deep" ? "browser-deep-token" : "browser-test-token" } });
    expect(r.ok()).toBe(true);
    return (await r.text()).trim().split("\n").map(line => JSON.parse(line));
  }
  const text = "Interrupted café 😀.\r\n" + deepEssay;
  const interrupted = await post(text);
  expect(interrupted.map(e => e.type)).toEqual(["accepted", "progress", "sentences", "error"]);
  const fallback = await post(text, "deep", interrupted.at(-1).retryToken);
  const done = fallback.at(-1);
  expect(done.type).toBe("result");
  await expect.poll(async () => (await (await request.get(
    "http://127.0.0.1:4328/stored?id=" + done.checkId)).json())?.p_mode).toBe("deep");
  expect((await post(text)).map(e => e.type)).toEqual(["result"]);
  expect((await post(text, "quick"))[0].type).toBe("accepted");
  const variant = text.replace("\r\n", "\n").normalize("NFD");
  const fresh = await post(variant);
  expect(fresh[0].type).toBe("accepted");
  const sentence = fresh.find(e => e.type === "sentences").items[0];
  expect(variant.slice(sentence.start, sentence.end)).toBe("Interrupted café 😀.".normalize("NFD"));
});

test("withholds a Deep verdict when a promised chunk never arrives", async ({ request }) => {
  const input = { text: "Missing chunk. " + deepEssay, mode: "deep", turnstileToken: "browser-deep-token" };
  const response = await request.post("/api/checks", { data: input });
  const records = (await response.text()).trim().split("\n").map(line => JSON.parse(line));
  expect(records[0]).toMatchObject({ type: "accepted", chunks: 3 });
  expect(records.filter(event => event.type === "sentences")).toHaveLength(2);
  expect(records.some(event => event.type === "result")).toBe(false);
  expect(records.at(-1)).toMatchObject({ type: "error", code: "internal", retryable: true });
  const retry = await request.post("/api/checks", { data: { ...input, retryToken: records.at(-1).retryToken } });
  const fallback = (await retry.text()).trim().split("\n").map(line => JSON.parse(line));
  expect(fallback[0]).toMatchObject({ type: "accepted", backend: "mlx-cuda" });
  expect(fallback.at(-1)).toMatchObject({ type: "error", retryable: false });
});

type ReportData = {
  reliability_bins: { count: number; mean_score: number | null; observed_fraction: number | null }[];
  metrics: Record<string, { fpr_high: { denominator: number } }>;
};
const deepReport: ReportData = JSON.parse(readFileSync(
  new URL("../../../eval/reports/phase-1/report.json", import.meta.url), "utf8",
));

test("methodology shows measured cohorts separately and explains a change in the base rate", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Methodology" }).click();
  await expect(page.getByRole("heading", { name: "Calibration", exact: true })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "TOEFL essays" })).toBeVisible();
  const evidence = page.getByRole("region", { name: "Deep evaluation" });
  const bins = deepReport.reliability_bins.filter(bin => bin.count > 0);
  if (bins.length) {
    const chart = evidence.getByRole("img", { name: "Calibration" });
    await expect(chart).toBeVisible();
    await expect(chart.locator("circle")).toHaveCount(bins.length);
    await evidence.getByText("Read chart values", { exact: true }).click();
    const values = evidence.locator("figure tbody tr");
    await expect(values).toHaveCount(bins.length);
    const percent = new Intl.NumberFormat("en", { style: "percent", maximumFractionDigits: 1 });
    for (const [i, bin] of bins.entries()) {
      expect(bin.mean_score).not.toBeNull();
      expect(bin.observed_fraction).not.toBeNull();
      await expect(values.nth(i).getByRole("cell")).toHaveText([
        percent.format(bin.mean_score!), percent.format(bin.observed_fraction!), String(bin.count),
      ]);
    }
    const all = evidence.getByRole("row").filter({ has: page.getByRole("rowheader", { name: "All documents", exact: true }) });
    await expect(all.getByRole("cell").first()).toHaveText(String(deepReport.metrics.pooled.fpr_high.denominator));
  } else {
    await expect(evidence.getByText("The Deep report has no held-out calibration measurements yet.")).toBeVisible();
  }
  await page.getByRole("combobox").selectOption("5");
  await expect(page.getByRole("status")).toContainText("40 AI essays and 19 human essays");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByText("Quick baseline", { exact: true }).first().click();
  await expect(page.getByText("quick-m6-fp32-v0", {exact: false})).toBeVisible();
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/zh-HK/methodology");
  await expect(page.getByRole("heading", { name: "檢測方法" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});


test("a Deep browser retry discards the interrupted heatmap before replaying chunks", async ({ page, request }) => {
  let attempts = 0;
  page.on("request", (req) => { if (new URL(req.url()).pathname === "/api/checks") attempts++; });
  await page.goto("/");
  await page.getByRole("radio", { name: "Deep check" }).check();
  await page.getByRole("textbox").fill("Interrupted browser draft. " + deepEssay);
  await page.getByRole("button", { name: "Check my essay" }).click();
  await expect.poll(() => attempts).toBe(2);
  const map = page.getByRole("region", { name: "Sentence heatmap" });
  await expect(map.locator(".sentence-marker")).toHaveCount(1);
  await expect(map.getByText("1 sentence read so far")).toBeVisible();
  await request.get("http://127.0.0.1:4328/continue-heatmap?fixture=interrupted");
  await expect(map.locator(".sentence-marker")).toHaveCount(33);
  await expect(page.getByText("Likely range 48–75")).toBeVisible();
});
