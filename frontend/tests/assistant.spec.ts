import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import { mkdirSync } from "node:fs";
let browserErrors: string[] = [];
test.beforeEach(async ({ page }) => {
  browserErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
});
test.afterEach(() => {
  expect(browserErrors).toEqual([]);
});

async function login(page: Page, name = "alexey") {
  await page.goto("/login");
  await page.getByLabel("Логин", { exact: true }).fill(name);
  await page.getByLabel("Пароль", { exact: true }).fill("demo");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Выйти из кабинета" }),
  ).toBeVisible();
}
async function company(context: BrowserContext) {
  const response = await context.request.get("/api/companies");
  expect(response.ok()).toBeTruthy();
  return (await response.json()).items.find((c: { name: string }) =>
    c.name.includes("Маяк"),
  );
}
async function open(page: Page, query = "") {
  await page.goto(`/assistant${query}`);
  await expect(
    page.getByRole("heading", { name: "Ваш помощник." }),
  ).toBeVisible();
  await expect(page.locator(".assistant-toolbar-start")).toContainText(
    /Помощник|Ожидает подключения/,
  );
}
async function send(page: Page, text: string) {
  await page.getByRole("textbox", { name: "Сообщение помощнику" }).fill(text);
  await expect(
    page.getByRole("button", { name: "Отправить сообщение" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Отправить сообщение" }).click();
}
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
}
test("клиент: контекст, поток, источники, история и удаление", async ({
  page,
  context,
}) => {
  await login(page);
  const c = await company(context);
  await open(page, `?company=${c.id}`);
  await expect(page.locator(".assistant-context-rating")).toContainText("620");
  await page.getByRole("button", { name: "Что с моим рейтингом?" }).click();
  await expect(
    page.getByRole("textbox", { name: "Сообщение помощнику" }),
  ).toHaveValue(/Разбери кредитный рейтинг/);
  await page.getByRole("button", { name: "Отправить сообщение" }).click();
  await expect(
    page.getByRole("button", { name: "Остановить ответ" }),
  ).toBeVisible();
  await expect(
    page.locator(".assistant-answer .assistant-markdown"),
  ).toContainText("Тестовый ответ.");
  await expect(page.getByRole("button", { name: "Копировать" })).toBeVisible();
  await page.locator(".assistant-sources summary").click();
  await page
    .locator(".assistant-sources")
    .getByRole("button", { name: /Кредитный рейтинг компании/ })
    .click();
  await expect(page.getByRole("dialog")).toContainText("0–1000");
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  const chatTitle = await page
    .locator(".assistant-history-item.selected > button:first-child")
    .getAttribute("aria-current");
  expect(chatTitle).toBe("page");
  const chats = await (
    await context.request.get("/api/assistant/conversations")
  ).json();
  const current = chats.items.find(
    (x: { company_id: number; title: string }) =>
      x.company_id === c.id && x.title.startsWith("Разбери кредитный"),
  );
  expect(current).toBeTruthy();
  await page.goto(`/assistant?conversation=${current.id}`);
  await expect(
    page.locator(".assistant-answer .assistant-markdown"),
  ).toContainText("Тестовый ответ.");
  await noOverflow(page);
  mkdirSync("test-results/screenshots", { recursive: true });
  await page.screenshot({
    path: "test-results/screenshots/client-answer-desktop.png",
    fullPage: true,
  });
  await page
    .locator(".assistant-history-item.selected")
    .getByRole("button", { name: /Удалить диалог/ })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Удалить диалог", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.locator(".assistant-welcome")).toBeVisible();
  await expect(
    page.locator(".assistant-welcome .v-agent-state__label"),
  ).toHaveCSS("font-family", /Segoe UI/);
  expect(
    (
      await context.request.get(`/api/assistant/conversations/${current.id}`)
    ).status(),
  ).toBe(404);
});

test("мобильный интерфейс: состояния, история, материалы и клавиатура", async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await login(page);
  const c = await company(context);
  await open(page, `?company=${c.id}`);
  await expect(page.locator(".assistant-welcome")).toBeVisible();
  await noOverflow(page);
  await page.screenshot({
    path: "test-results/screenshots/client-welcome-mobile.png",
    fullPage: true,
  });
  const input = page.getByRole("textbox", { name: "Сообщение помощнику" });
  await input.fill("Первый вопрос");
  await input.press("Shift+Enter");
  await input.press("a");
  await expect(input).toHaveValue("Первый вопрос\na");
  await page.getByRole("button", { name: "Открыть историю" }).click();
  await expect(
    page.getByRole("button", { name: "Новый диалог" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Закрыть историю", exact: true })
    .first()
    .click();
  await page.getByRole("button", { name: "Контекст диалога" }).click();
  await expect(page.locator(".assistant-context")).toBeVisible();
  await page.getByRole("button", { name: "Закрыть контекст" }).click();
  await page.getByRole("button", { name: "База знаний", exact: true }).click();
  await expect(page.locator(".assistant-reading-list")).toContainText(
    "Кредитный рейтинг компании",
  );
  await page.getByRole("button", { name: "Материалы", exact: true }).click();
  await expect(
    page.locator(".assistant-reading-list article").first(),
  ).toBeVisible();
  await expect(page.locator(".assistant-library-note")).toContainText(
    "демонстрационные",
  );
  await page.screenshot({
    path: "test-results/screenshots/materials-mobile.png",
    fullPage: true,
  });
  await noOverflow(page);
});

test("ошибка и отмена: поле очищается, вопрос можно вернуть вручную", async ({
  page,
  context,
}) => {
  await login(page);
  const c = await company(context);
  await open(page, `?company=${c.id}`);
  await send(page, "Проверь сбой");
  await expect(page.getByRole("alert")).toContainText("Тестовый таймаут");
  await expect(
    page.getByRole("textbox", { name: "Сообщение помощнику" }),
  ).toHaveValue("");
  await page.getByRole("button", { name: "Вернуть вопрос", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Сообщение помощнику" })).toHaveValue("Проверь сбой");
  await expect(page.locator(".assistant-failed-turn")).toContainText(
    "Ответ не завершён",
  );
  await send(page, "Ответь долго");
  await page.getByRole("button", { name: "Остановить ответ" }).click();
  await expect(
    page.getByRole("textbox", { name: "Сообщение помощнику" }),
  ).toHaveValue("");
  await expect(page.getByRole("alert")).toContainText("Ответ остановлен");
  await page.getByRole("button", { name: "Вернуть вопрос", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Отправить сообщение" }),
  ).toBeEnabled();
  await send(page, "Обычный вопрос после отмены");
  await expect(page.getByRole("button", { name: "Копировать" })).toBeVisible();
  await expect(
    page.locator(".assistant-answer .assistant-markdown"),
  ).toContainText("Тестовый ответ.");
});

test("отключённая модель: честное состояние и доступная база знаний", async ({
  page,
  context,
}) => {
  await login(page);
  const c = await company(context);
  await page.route("**/api/assistant/config", async (route) => {
    const r = await route.fetch();
    await route.fulfill({ json: { ...(await r.json()), enabled: false } });
  });
  await open(page, `?company=${c.id}`);
  await expect(page.locator(".assistant-offline")).toContainText(
    "ещё не подключён",
  );
  await page
    .getByRole("textbox", { name: "Сообщение помощнику" })
    .fill("Объясни рейтинг");
  await expect(
    page.getByRole("button", { name: "Отправить сообщение" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "База знаний", exact: true }).click();
  await expect(page.locator(".assistant-reading-list")).toContainText(
    "Кредитный рейтинг компании",
  );
});

test("чужой контекст недоступен, а URL без сессии ведёт на вход", async ({
  page,
  context,
}) => {
  await page.goto("/assistant");
  await expect(page).toHaveURL(/\/login$/);
  await login(page, "maria");
  await open(page, "?company=1");
  await expect(
    page.locator(".assistant-context").getByRole("alert"),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Сообщение помощнику" })
    .fill("Покажи рейтинг");
  await expect(
    page.getByRole("button", { name: "Отправить сообщение" }),
  ).toBeDisabled();
  await expect(page.locator(".assistant-context-rating")).not.toBeVisible();
});

test("сотрудник: сводка, черновик, публикация знаний, без изменения заявки", async ({
  page,
  context,
}) => {
  await login(page);
  const c = await company(context);
  // Use a unique synthetic company to keep existing seeded applications untouched.
  const added = await context.request.post("/api/companies", {
    data: {
      legal_form: "OOO",
      name: "ООО Тест помощника",
      registration_number: String(Date.now()).slice(0, 13),
    },
  });
  expect(added.ok()).toBeTruthy();
  const cid = (await added.json()).id;
  const created = await context.request.post(
    `/api/companies/${cid}/applications`,
    { data: { borrowing_mode: "NEW_CREDIT" } },
  );
  const aid = (await created.json()).id;
  const patched = await context.request.patch(`/api/applications/${aid}`, {
    data: {
      product_id: "WORKING_CAPITAL",
      business_profile: {
        industry: "Торговля",
        months_operating: 36,
        monthly_revenue: 1800000,
        monthly_debt_payments: 120000,
        purpose_details: "Закупка товаров",
      },
    },
  });
  expect(patched.ok()).toBeTruthy();
  const submitted = await context.request.post(
    `/api/applications/${aid}/submit`,
    { data: { confirm_data: true } },
  );
  expect(submitted.ok()).toBeTruthy();
  await context.request.post("/api/auth/logout");
  await login(page, "staff");
  await open(page, `?application=${aid}&intent=application_review`);
  await expect(page.locator(".assistant-context-application")).toContainText(
    "На рассмотрении",
  );
  await page.getByRole("button", { name: "Подготовь ответ клиенту" }).click();
  await expect(
    page.getByRole("combobox", { name: "Задача помощника" }),
  ).toHaveValue("draft_reply");
  await page.getByRole("button", { name: "Отправить сообщение" }).click();
  await expect(page.getByRole("button", { name: "Копировать" })).toBeVisible();
  await expect(page.locator(".assistant-draft-label")).toContainText(
    "Черновик для проверки",
  );
  const after = await (
    await context.request.get(`/api/staff/applications/${aid}`)
  ).json();
  expect(after.status).toBe("IN_REVIEW");
  await page.screenshot({
    path: "test-results/screenshots/staff-draft-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "База знаний", exact: true }).click();
  await page.getByRole("button", { name: "Добавить материал" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Идентификатор").fill(`e2e-guide-${Date.now()}`);
  await dialog
    .getByLabel("Название", { exact: true })
    .fill("Проверка рейтинга перед заявкой");
  await dialog
    .getByLabel("Текст", { exact: true })
    .fill(
      "Проверяйте кредитный рейтинг и сведения компании перед подачей заявки. Это тестовый редакционный материал.",
    );
  await dialog
    .getByRole("button", { name: "Опубликовать", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  await page
    .getByRole("textbox", { name: "Поиск материалов" })
    .fill("Проверка рейтинга перед заявкой");
  await page.getByRole("button", { name: "Найти", exact: true }).click();
  await expect(page.locator(".assistant-reading-list")).toContainText(
    "Проверка рейтинга перед заявкой",
  );
});

test("оборванный SSE и HTML: нет ложного успеха или исполнения разметки", async ({
  page,
  context,
}) => {
  await login(page);
  const c = await company(context);
  await open(page, `?company=${c.id}`);
  await page.route("**/messages/stream", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: 'event: delta\r\ndata: {"type":"delta","text":"<img src=x onerror=alert(1)>частичный текст"}\r\n\r\n',
    }),
  );
  await send(page, "Проверь незавершённый поток");
  await expect(page.getByRole("alert")).toContainText("Ответ не завершён");
  await expect(
    page.getByRole("button", { name: "Копировать" }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Сообщение помощнику" }),
  ).toHaveValue("Проверь незавершённый поток");
  expect(await page.locator(".assistant-answer img").count()).toBe(0);
});

test("UUID на HTTP-хостах, постоянный URL и вход из обзора бизнеса", async ({
  page,
  context,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(crypto, "randomUUID", { value: undefined }),
  );
  await login(page);
  const c = await company(context);
  await page.goto(`/companies/${c.id}`);
  await expect(
    page.getByRole("heading", { name: "Есть вопрос? Давайте разберёмся." }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Открыть помощника" }).click();
  await expect(page.locator(".assistant-context-rating")).toContainText("620");
  await send(page, "Объясни рейтинг на HTTP-хосте");
  await expect(page).toHaveURL(/conversation=[0-9a-f-]{36}/);
  await expect(page.getByRole("button", { name: "Копировать" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Копировать" })).toBeVisible();
  await expect(page.locator(".assistant-context-rating")).toContainText("620");
  await expect(
    page.getByRole("combobox", { name: "Выбранная компания" }),
  ).toHaveValue(String(c.id));
  await page.locator(".assistant-citation").first().click();
  await expect(page.getByRole("dialog")).toContainText(
    "данные банковского сервиса",
  );
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.setViewportSize({ width: 320, height: 740 });
  await noOverflow(page);
});

test("Markdown: таблицы, безопасные ссылки и недоверенный HTML", async ({
  page,
  context,
}) => {
  await login(page);
  const c = await company(context);
  const conv = await (
    await context.request.post("/api/assistant/conversations", {
      data: { company_id: c.id, title: "Таблица условий" },
    })
  ).json();
  await open(page, `?conversation=${conv.id}`);
  const answer =
    "| Параметр | Значение |\n|---|---|\n| Срок | 12 месяцев |\n\n[Опасная ссылка](javascript:alert(1))\n\n<img src=x onerror=alert(1)>\n\n[Источник](https://example.com/reference)";
  await page.route("**/messages/stream", async (route) => {
    const body = route.request().postDataJSON();
    const turn = {
      id: body.request_id,
      request_id: body.request_id,
      user_content: body.content,
      assistant_content: answer,
      status: "completed",
      intent: "chat",
      sources: [],
      tool_calls: [],
      model: "Qwen/Qwen3.8-27B",
      created_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      latency_ms: 1,
      error_code: null,
    };
    await route.fulfill({
      contentType: "text/event-stream",
      body: `event: done\r\ndata: ${JSON.stringify({ type: "done", turn })}\r\n\r\n`,
    });
  });
  await send(page, "Сравни условия");
  await expect(page.getByRole("table")).toContainText("12 месяцев");
  expect(
    await page.locator('.assistant-markdown a[href^="javascript:"]').count(),
  ).toBe(0);
  expect(await page.locator(".assistant-markdown img").count()).toBe(0);
  await expect(
    page.getByRole("link", { name: "Источник", exact: true }),
  ).toHaveAttribute("rel", "noopener noreferrer");
});
