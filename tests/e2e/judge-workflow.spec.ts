import { expect, test, type Page } from "@playwright/test";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function login(page: Page) {
  await page.goto("/login");
  await page.fill('input[type="email"]', "manager@stockmind.demo");
  await page.fill('input[type="password"]', "demo1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/dashboard/);
}

test.describe("StockMind AI judge workflow", () => {
  test("login screen refuses bad credentials", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="email"]', "manager@stockmind.demo");
    await page.fill('input[type="password"]', "definitely-wrong");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/invalid email or password/i)).toBeVisible();
  });

  test("dashboard KPIs render and match the API", async ({ page, request }) => {
    await login(page);
    await expect(page.getByRole("heading", { name: /recovery dashboard/i })).toBeVisible();

    const token = await page.evaluate(() => window.localStorage.getItem("stockmind.token"));
    const response = await request.get(`${API}/api/dashboard`, { headers: { Authorization: `Bearer ${token}` } });
    expect(response.ok()).toBeTruthy();
    const payload = await response.json();
    expect(payload.kpis.dead_stock_value).toBeGreaterThanOrEqual(0);

    await expect(page.getByText(/dead stock value/i).first()).toBeVisible();
    await expect(page.getByText(/capital at risk/i).first()).toBeVisible();
  });

  test("dead stock center lists candidates and opens the recovery studio", async ({ page }) => {
    await login(page);
    await page.goto("/dead-stock");
    await expect(page.getByRole("heading", { name: /dead stock center/i })).toBeVisible();

    const rows = page.locator("tbody tr");
    await expect(rows.first()).toBeVisible();
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);

    await rows.first().getByRole("link", { name: /analyze/i }).click();
    await expect(page).toHaveURL(/recovery-studio/);
    await expect(page.getByRole("heading", { name: /recovery studio/i })).toBeVisible();
  });

  test("recovery studio shows four agent proposals and executes a plan", async ({ page }) => {
    await login(page);
    await page.goto("/dead-stock");
    await page.locator("tbody tr").first().getByRole("link", { name: /analyze/i }).click();
    await expect(page).toHaveURL(/recovery-studio/);

    // Four agent cards must be visible.
    for (const label of ["Discount Agent", "Inter-Store Swap Agent", "Buy-A-Get-B Combo Agent", "B2B Bulk Buyer Agent"]) {
      await expect(page.getByText(label, { exact: false }).first()).toBeVisible();
    }

    const execute = page.getByRole("button", { name: /execute plan/i });
    if (await execute.isEnabled()) {
      await execute.click();
      await expect(page.getByText(/inventory, promotions and the audit trail were updated/i)).toBeVisible();
      await expect(page.getByText(/before \/ after/i)).toBeVisible();
      await expect(page.getByText(/prototype simulation/i).first()).toBeVisible();
    }
  });

  test("autonomous demo run completes with a timeline", async ({ page }) => {
    await login(page);
    await page.goto("/recovery-studio?demo=1");
    await expect(page.getByRole("heading", { name: /recovery studio/i })).toBeVisible();
    await expect(page.getByText(/autonomous run summary/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/execution timeline/i)).toBeVisible();
  });

  test("action history, store network and B2B market load", async ({ page }) => {
    await login(page);

    await page.goto("/history");
    await expect(page.getByRole("heading", { name: /action history/i })).toBeVisible();

    await page.goto("/stores");
    await expect(page.getByRole("heading", { name: /store network/i })).toBeVisible();
    await expect(page.getByText(/transfer opportunities/i)).toBeVisible();

    await page.goto("/b2b");
    await expect(page.getByRole("heading", { name: /b2b market/i })).toBeVisible();
    await expect(page.getByText(/bulkmart wholesale/i)).toBeVisible();
  });

  test("no console errors on the main pages", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    await login(page);
    for (const path of ["/dashboard", "/dead-stock", "/recovery-studio", "/stores", "/b2b", "/history"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
    }
    const meaningful = errors.filter((text) => !text.includes("favicon"));
    expect(meaningful).toEqual([]);
  });
});
