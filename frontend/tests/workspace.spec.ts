import { expect, test } from "@playwright/test";

test("scan, graph, update options, CVE lookup and saved settings", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Проверка зависимостей Python" })).toBeVisible();
  await page.getByRole("link", { name: "Проверить проект", exact: true }).click();
  await page.getByLabel("Имя пользователя").fill(`e2e_${Date.now()}`);
  await page.getByLabel("Пароль", { exact: true }).fill("Paxveil-E2E-2026!");
  await page.getByRole("button", { name: "Создать аккаунт", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Проекты", exact: true })).toBeVisible();

  await page.locator(".empty-state").getByRole("button", { name: "Добавить проект", exact: true }).click();
  await page.getByLabel("Название проекта").fill("Python acceptance");
  await page.getByLabel("Файл зависимостей").setInputFiles({
    name: "requirements.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("requests==2.31.0\n"),
  });
  await page.getByRole("button", { name: "Создать проект и проверить", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Python acceptance", exact: true })).toBeVisible();
  const projectUrl = page.url();
  await expect(page.getByRole("heading", { name: /^Уязвимости/ })).toBeVisible({ timeout: 120_000 });
  await expect(page.locator(".findings-table tbody tr").first()).toBeVisible();
  await page.getByRole("button", { name: /Подробнее/ }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();

  await page.getByRole("tab", { name: "Зависимости", exact: true }).click();
  await expect(page.getByRole("group", { name: "Граф зависимостей" })).toBeVisible();
  await page.getByRole("button", { name: /requests 2.31.0/ }).click();
  await expect(page.locator(".graph-detail")).toContainText("requests");
  await page.getByRole("tab", { name: "Обновления", exact: true }).click();
  await page.getByRole("button", { name: "Рассчитать варианты", exact: true }).click();
  await expect(page.locator(".strategy")).toHaveCount(3, { timeout: 120_000 });

  await page.getByRole("button", { name: "Мониторинг", exact: true }).click();
  await expect(page.getByRole("button", { name: "Мониторинг включён", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Python acceptance", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Мониторинг включён", exact: true })).toBeVisible();

  await page.goto("/app/fire");
  await page.getByLabel("Номер CVE").fill("CVE-2024-35195");
  await page.getByRole("button", { name: "Проверить проекты", exact: true }).click();
  await expect(page.locator(".fire-match")).toContainText("requests", { timeout: 60_000 });

  await page.goto("/app/settings");
  await expect(page.getByLabel("Часовой пояс")).toHaveValue("Europe/Moscow");
  await page.getByRole("checkbox", { name: "Ежедневная сводка" }).check();
  await page.getByRole("button", { name: "Сохранить настройки", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Настройки сохранены");
  await page.reload();
  await expect(page.getByRole("checkbox", { name: "Ежедневная сводка" })).toBeChecked();
  await page.getByRole("button", { name: "Получить код", exact: true }).click();
  await expect(page.locator(".copy-command")).toContainText("/link");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Открыть меню", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Разделы приложения" })).toBeVisible();
  await page.getByRole("link", { name: "История", exact: true }).click();
  await expect(page.getByRole("heading", { name: "История проверок", exact: true })).toBeVisible();
  await page.goto(projectUrl);
  await page.getByRole("button", { name: "Удалить проект", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Удалить проект", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Проекты", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("unsupported filename shows validation and keeps the upload open", async ({ page, request }) => {
  const registration = await request.post("/api/auth/register", {
    data: { username: `invalid_${Date.now()}`, password: "Paxveil-E2E-2026!" },
  });
  expect(registration.ok()).toBeTruthy();
  await page.context().addCookies(await request.storageState().then(state => state.cookies));
  await page.goto("/app");
  await page.locator(".empty-state").getByRole("button", { name: "Добавить проект", exact: true }).click();
  await page.getByLabel("Название проекта").fill("Invalid dependencies");
  await page.getByLabel("Файл зависимостей").setInputFiles({
    name: "not-supported.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not a requirement!\n"),
  });
  await page.getByRole("button", { name: "Создать проект и проверить", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Поддерживаются");
  await expect(page.getByRole("dialog")).toBeVisible();
});
