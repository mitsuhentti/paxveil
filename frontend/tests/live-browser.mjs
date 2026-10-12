import { chromium, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

const base = process.env.PAXVEIL_WEB_URL || "http://127.0.0.1:3000";
const browser = await chromium.connectOverCDP(
  process.env.PLAYWRIGHT_CDP_URL || "http://127.0.0.1:9223",
  { timeout: 15000 },
);
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
const results = [];
const started = new Date();
const screenshots = join(process.cwd(), "..", "docs", "screenshots");
let projectUrl;

page.on("pageerror", error => errors.push(error.message));
await mkdir(screenshots, { recursive: true });

async function check(name, action) {
  const start = Date.now();
  await action();
  results.push({ name, passed: true, milliseconds: Date.now() - start });
  console.log(`PASS ${name}`);
}

try {
  await check("Landing and signup navigation", async () => {
    await page.goto(base);
    await expect(page.getByRole("heading", { name: "Проверка зависимостей Python" })).toBeVisible();
    await page.screenshot({ path: join(screenshots, "landing-desktop.png"), fullPage: true });
    await page.getByRole("link", { name: "Проверить проект", exact: true }).click();
  });
  await check("Cookie authentication and empty workspace", async () => {
    await page.getByLabel("Имя пользователя").fill(`browser_${Date.now()}`);
    await page.getByLabel("Пароль", { exact: true }).fill("Paxveil-Browser-2026!");
    await page.getByRole("button", { name: "Создать аккаунт", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Проекты", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Добавьте первый проект", exact: true })).toBeVisible();
  });
  await check("Multipart upload and known-vulnerability report", async () => {
    await page.locator(".empty-state").getByRole("button", { name: "Добавить проект", exact: true }).click();
    await page.getByLabel("Название проекта").fill("Public Python dependencies");
    await page.getByLabel("Файл зависимостей").setInputFiles({
      name: "requirements.txt", mimeType: "text/plain", buffer: Buffer.from("requests==2.31.0\n"),
    });
    await page.getByRole("button", { name: "Создать проект и проверить", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Public Python dependencies", exact: true })).toBeVisible();
    projectUrl = page.url();
    await expect(page.getByRole("heading", { name: /^Уязвимости/ })).toBeVisible({ timeout: 120000 });
    await expect(page.locator(".findings-table tbody tr").first()).toBeVisible();
    await page.screenshot({ path: join(screenshots, "report-desktop.png"), fullPage: true });
  });
  await check("Search, filter and advisory references", async () => {
    await page.getByLabel("Поиск уязвимостей").fill("does-not-exist");
    await expect(page.getByRole("heading", { name: "Нет совпадений с фильтром", exact: true })).toBeVisible();
    await page.getByLabel("Поиск уязвимостей").fill("requests");
    await expect(page.locator(".findings-table tbody tr").first()).toBeVisible();
    await page.getByRole("button", { name: /Подробнее/ }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("dialog").locator(".external-link").first()).toBeVisible();
    await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  });
  await check("Interactive graph and root path", async () => {
    await page.getByRole("tab", { name: "Зависимости", exact: true }).click();
    await expect(page.getByRole("group", { name: "Граф зависимостей" })).toBeVisible();
    await page.getByRole("button", { name: /requests 2.31.0/ }).click();
    await expect(page.locator(".graph-detail")).toContainText("requests");
    await page.screenshot({ path: join(screenshots, "graph-desktop.png"), fullPage: true });
  });
  await check("Async FixLab compares three computed strategies", async () => {
    await page.getByRole("tab", { name: "Обновления", exact: true }).click();
    await page.getByRole("button", { name: "Рассчитать варианты", exact: true }).click();
    await expect(page.locator(".strategy")).toHaveCount(3, { timeout: 180000 });
    await page.screenshot({ path: join(screenshots, "fixlab-desktop.png"), fullPage: true });
  });
  await check("Watch survives page reload", async () => {
    await page.getByRole("button", { name: "Мониторинг", exact: true }).click();
    await expect(page.getByRole("button", { name: "Мониторинг включён", exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Мониторинг включён", exact: true })).toBeVisible();
  });
  await check("CVE lookup matches the saved requests version", async () => {
    await page.goto(`${base}/app/fire`);
    await page.getByLabel("Номер CVE").fill("CVE-2024-35195");
    await page.getByRole("button", { name: "Проверить проекты", exact: true }).click();
    await expect(page.locator(".fire-match")).toContainText("requests", { timeout: 60000 });
    await page.screenshot({ path: join(screenshots, "fire-drill-desktop.png"), fullPage: true });
  });
  await check("Settings persistence, Telegram link code and themes", async () => {
    await page.goto(`${base}/app/settings`);
    await expect(page.getByLabel("Часовой пояс")).toHaveValue("Europe/Moscow");
    await page.getByRole("checkbox", { name: "Ежедневная сводка" }).check();
    await page.getByRole("button", { name: "Сохранить настройки", exact: true }).click();
    await expect(page.locator(".toast")).toContainText("Настройки сохранены");
    await page.reload();
    await expect(page.getByRole("checkbox", { name: "Ежедневная сводка" })).toBeChecked();
    await page.getByRole("button", { name: "Получить код", exact: true }).click();
    await expect(page.locator(".copy-command")).toContainText("/link");
    await page.getByRole("button", { name: "Тёмная тема", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.getByRole("button", { name: "Светлая тема", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });
  await check("Dashboard and mobile history are responsive", async () => {
    await page.goto(`${base}/app`);
    await expect(page.locator(".project-row")).toContainText("Public Python dependencies");
    await page.screenshot({ path: join(screenshots, "dashboard-desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Открыть меню", exact: true }).click();
    await page.getByRole("link", { name: "История", exact: true }).click();
    await expect(page.getByRole("heading", { name: "История проверок", exact: true })).toBeVisible();
    await page.goto(projectUrl);
    await expect(page.getByRole("heading", { name: /^Уязвимости/ })).toBeVisible();
    await page.screenshot({ path: join(screenshots, "report-mobile.png"), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow).toBe(false);
  });
  await check("Unsupported filename shows upload validation", async () => {
    await page.getByRole("button", { name: "Новый проект", exact: true }).click();
    await page.getByLabel("Название проекта").fill("Invalid input check");
    await page.getByLabel("Файл зависимостей").setInputFiles({
      name: "invalid.txt", mimeType: "text/plain", buffer: Buffer.from("not-a-valid-requirement!\n"),
    });
    await page.getByRole("button", { name: "Создать проект и проверить", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("Поддерживаются");
    await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  });
  await check("Saved project can be removed", async () => {
    await page.getByRole("button", { name: "Удалить проект", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Удалить проект", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Проекты", exact: true })).toBeVisible();
  });
  await check("No uncaught browser errors", async () => { expect(errors).toEqual([]); });
} catch (error) {
  results.push({ name: "Browser flow failed", passed: false, error: error.message });
  await page.screenshot({ path: join(screenshots, "browser-failure.png"), fullPage: true });
  console.error(error);
  process.exitCode = 1;
} finally {
  await mkdir("test-results", { recursive: true });
  await writeFile("test-results/live-browser.json", JSON.stringify({
    started: started.toISOString(), finished: new Date().toISOString(), base, results, errors,
  }, null, 2));
  await context.close();
  await browser.close();
}
