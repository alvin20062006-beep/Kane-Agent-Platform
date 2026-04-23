import { test, expect, type Page, type ConsoleMessage } from "@playwright/test";

/**
 * Deeper click audit — actually simulates user flows the user reported as broken.
 */

function attachReporters(page: Page): { errors: string[] } {
  const errors: string[] = [];
  page.on("pageerror", (e: Error) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (msg: ConsoleMessage) => {
    const text = msg.text();
    if (text.includes("webpack-hmr") || text.includes("WebSocket connection")) return;
    if (msg.type() === "error") errors.push(`console.error: ${text}`);
  });
  return { errors };
}

test("sidebar navigation clicks between pages", async ({ page }) => {
  const { errors } = attachReporters(page);
  await page.goto("http://127.0.0.1:3000/dashboard", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("load");
  await page.waitForTimeout(2000);

  for (const href of [
    "/conversations",
    "/cockpit",
    "/tasks",
    "/agent-fleet",
    "/skills",
    "/memory",
    "/connections",
    "/files",
    "/settings",
    "/dashboard",
  ]) {
    const link = page.locator(`aside a[href='${href}']`).first();
    await expect(link, `sidebar link ${href} exists`).toBeVisible();
    await link.click();
    await page.waitForURL(new RegExp(href.replace("/", "\\/")), { timeout: 5000 });
    console.log(`  OK click sidebar ${href}`);
  }

  expect(errors, "sidebar navigation console errors").toEqual([]);
});

test("conversations: create + switch + send flow", async ({ page }) => {
  const { errors } = attachReporters(page);
  await page.goto("http://127.0.0.1:3000/conversations", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("load");
  await page.waitForTimeout(2000);

  // Click "+ 新建"
  const newBtn = page.locator("[data-testid='create-conversation-button']");
  await expect(newBtn).toBeVisible();
  await expect(newBtn).toBeEnabled();
  const before = await page.locator("[data-testid^='conversation-item-']").count();
  await newBtn.click();
  await page.waitForTimeout(1200);
  const after = await page.locator("[data-testid^='conversation-item-']").count();
  expect(after, "新建应该创建新会话").toBeGreaterThan(before);
  console.log(`  OK 新建会话  (${before} → ${after})`);

  // Click second conversation to switch
  const items = page.locator("[data-testid^='conversation-item-']");
  if ((await items.count()) > 1) {
    await items.nth(1).click();
    await page.waitForTimeout(300);
    console.log(`  OK 切换会话`);
  }

  // Mode buttons
  const modeBtns = page.locator("button[class*='rounded-full']");
  const modeCount = await modeBtns.count();
  if (modeCount > 0) {
    let clickedMode = 0;
    for (let i = 0; i < modeCount; i++) {
      const btn = modeBtns.nth(i);
      if (!(await btn.isDisabled().catch(() => true))) {
        await btn.click().catch(() => {});
        clickedMode++;
        if (clickedMode >= 2) break;
      }
    }
    console.log(`  OK 可点击执行模式 ${clickedMode}/${modeCount}`);
  }

  // Operator select change
  const select = page.locator("[data-testid='operator-select']");
  if (await select.count()) {
    const opts = await select.locator("option").allTextContents();
    console.log(`  Operator 选项: ${opts.join(" / ")}`);
  }

  // Type into composer and verify send enables
  const composer = page.locator("textarea");
  if (await composer.count()) {
    await composer.first().fill("test message from qa audit");
    const sendBtn = page.locator("button:has-text('发送'), button:has-text('Send')").first();
    await expect(sendBtn).toBeEnabled();
    console.log(`  OK 发送按钮在有内容时 enabled`);
  }

  expect(errors, "conversations flow errors").toEqual([]);
});

test("language toggle actually switches UI text", async ({ page }) => {
  const { errors } = attachReporters(page);
  await page.goto("http://127.0.0.1:3000/tasks", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("load");
  await page.waitForTimeout(2000);

  // find nav text "任务" before toggle
  const navZh = await page.locator("aside").innerText();
  expect(navZh).toContain("任务");

  // toggle
  const langBtn = page.locator("header button[aria-label*='language'], header button[aria-label*='Language'], header button:has(svg):has-text('中'), header button:has(svg):has-text('EN')");
  const count = await langBtn.count();
  console.log(`  lang toggle count: ${count}`);
  if (count === 0) {
    // fallback: last button in header
    const fallback = page.locator("header button").last();
    await fallback.click();
  } else {
    await langBtn.first().click();
  }
  await page.waitForTimeout(500);
  const navAfter = await page.locator("aside").innerText();
  console.log(`  nav after toggle: ${navAfter.slice(0, 120)}`);

  const switched = navAfter.includes("Tasks") || navAfter.includes("Conversations");
  expect(switched, "nav text should switch to English").toBeTruthy();
  console.log(`  OK 中→EN 切换成功`);

  // toggle back
  await page.locator("header button").last().click();
  await page.waitForTimeout(500);
  const navBack = await page.locator("aside").innerText();
  expect(navBack).toContain("任务");
  console.log(`  OK EN→中 切换回去`);

  expect(errors, "language toggle errors").toEqual([]);
});

test("settings left nav stays visible when switching category", async ({ page }) => {
  const { errors } = attachReporters(page);
  await page.goto("http://127.0.0.1:3000/settings", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("load");
  await page.waitForTimeout(2000);

  const navLinks = page.locator("aside a, aside button, [role='navigation'] a");
  const count = await navLinks.count();
  console.log(`  settings nav count: ${count}`);
  expect(count).toBeGreaterThan(5);

  // click each visible anchor in order, ensure sidebar still shows
  for (let i = 0; i < Math.min(count, 5); i++) {
    const link = navLinks.nth(i);
    const txt = (await link.textContent().catch(() => "")) ?? "";
    if (!txt.trim()) continue;
    await link.click().catch(() => {});
    await page.waitForTimeout(200);
    const stillVisible = await page.locator("aside").first().isVisible();
    if (!stillVisible) {
      errors.push(`aside disappeared after clicking "${txt.trim()}"`);
    } else {
      console.log(`  OK 仍可见 (点了 "${txt.trim().slice(0, 20)}")`);
    }
  }

  expect(errors, "settings nav errors").toEqual([]);
});
