# Руководство для фронтенда: API «Дело — кредиты для бизнеса»

Всё, что нужно, чтобы собрать клиентские экраны (§1–§14 инструкции) и панель сотрудника, не заглядывая в код бэкенда.

- **Боевой стенд:** `http://195.133.41.30`
- **Swagger (все эндпоинты и тела запросов):** `http://195.133.41.30/docs`
- **Реальные ответы сервера:** папка [`docs/api-examples/`](api-examples/), по файлу на каждый случай. Генерируются скриптом `backend/scripts/gen_examples.py`, поэтому совпадают с тем, что вернёт стенд.
- **Дизайн:** https://delo-credit-design-directions.cheery-tapir-6675.chatgpt.site, **вариант 4**. Тексты и порядок экранов брать оттуда.

---

## 0. Быстрый старт

| Логин | Пароль | Кто |
|---|---|---|
| `alexey` | `demo` | Алексей Морозов, клиент, 3 компании |
| `maria` | `demo` | Мария Ковалёва, клиент, 1 компания (для проверки изоляции) |
| `staff` | `demo` | Ирина Котова, сотрудник банка |

```bash
# сбросить стенд к исходным данным (удаляет все заявки и добавленные компании)
curl -X POST http://195.133.41.30/api/demo/reset
# выключить/включить симулятор бюро (показать «Рейтинг пока недоступен»)
curl -X POST http://195.133.41.30/api/demo/bureau -H 'Content-Type: application/json' -d '{"available": false}'
```

Стенд общий для всей команды: сброс стирает данные у всех.

---

## 1. Авторизация

`POST /api/auth/login` `{"login": "alexey", "password": "demo"}` → `{"user": {...}, "token": "..."}` и httpOnly-cookie `session`.

Поддерживаются два способа передать сессию:

1. **Bearer-токен (рекомендуется для разработки).** Сохраните `token` (например, в `localStorage`) и отправляйте заголовок `Authorization: Bearer <token>`. Работает с любого origin, в том числе с `localhost:5173` против стенда.
2. **Cookie.** Работает, только если фронт и API на одном сайте (один хост, например фронт раздаётся с того же сервера через nginx). Запросы делайте с `credentials: "include"`. С `localhost` на `195.133.41.30` браузер cookie не отправит: это разные сайты, а `SameSite=Lax`.

- `GET /api/auth/me` → `{"user": {"id", "login", "full_name", "first_name", "role"}}`. `role` принимает значения `CLIENT` или `EMPLOYEE`. Вызывать при старте приложения: так восстанавливается сессия после обновления страницы.
- `POST /api/auth/logout` удаляет cookie. Токен просто забудьте на клиенте.
- Без сессии → `401 UNAUTHORIZED`. Клиент на `/api/staff/*` или сотрудник на клиентских эндпоинтах → `403 FORBIDDEN`.

**CORS:** разрешены `http://localhost:5173`, `http://localhost:3000`, `http://127.0.0.1:5173`, `http://195.133.41.30`. Если нужен другой origin, его надо добавить в `CORS_ORIGINS` в `/opt/delo/.env` на сервере и выполнить `docker compose up -d`.

---

## 2. Общие соглашения

| Что | Как |
|---|---|
| Префикс | все пути начинаются с `/api` |
| Деньги | целые рубли (`1500000`). Форматирование с пробелами и `₽` делает фронт, на сервер отправляются только числа |
| Ставки | число с одной десятичной (`18.0`), «% годовых» |
| Сроки | целые месяцы |
| Даты | ISO-8601. Время в UTC, на стенде со смещением `+00:00`. Дата без времени — `YYYY-MM-DD` |
| `null` | значения нет, например рейтинг недоступен или параметр не выбран |

### Ошибки, формат всегда один

```json
{"error": {"code": "VALIDATION_ERROR", "message": "Проверьте введённые данные",
           "fields": {"amount": "Максимальная сумма для ИП — 3 000 000 ₽",
                      "business_profile.monthly_revenue": "Значение не может быть отрицательным"}}}
```

- `fields` — ключ имени поля и готовый текст ошибки, его показываем **рядом с полем**. Вложенные поля записываются через точку (`business_profile.industry`, `fields.monthly_revenue`).
- `message` — общий текст для тоста или баннера.
- При любой ошибке **не очищайте форму** (§8, §15).

| HTTP | `code` | Когда |
|---|---|---|
| 401 | `UNAUTHORIZED`, `INVALID_CREDENTIALS` | нет сессии или неверный пароль |
| 403 | `FORBIDDEN` | не та роль |
| 404 | `NOT_FOUND` | ресурса нет **или он чужой**. Сервер не раскрывает, что чужой ресурс существует |
| 409 | `INVALID_STATUS` | действие недоступно в текущем статусе (например, PATCH отправленной заявки) |
| 409 | `ALREADY_SUBMITTED`, `ALREADY_ACCEPTED` | повторная отправка или повторное принятие |
| 409 | `NO_LOANS_TO_REFINANCE` | у компании нет кредитов для рефинансирования |
| 409 | `LOAN_ALREADY_IN_APPLICATION` | по этому кредиту уже есть активная заявка |
| 409 | `DUPLICATE_COMPANY` | компания с таким номером уже добавлена |
| 409 | `NO_OPEN_REQUEST` | нет открытого запроса сведений |
| 422 | `VALIDATION_ERROR` | ошибки полей (см. `fields`) |
| 422 | `SAME_AS_REQUESTED` | (сотрудник) встречное предложение совпадает с запрошенным |

Примеры: [`unauthorized_401.json`](api-examples/unauthorized_401.json), [`draft_patch_error.json`](api-examples/draft_patch_error.json), [`submit_incomplete_422.json`](api-examples/submit_incomplete_422.json), [`submit_again_409.json`](api-examples/submit_again_409.json).

---

## 3. Справочники: `GET /api/config`

Без авторизации. Загрузить один раз при старте. **Лимиты и названия не хардкодить**, брать отсюда. Пример: [`config.json`](api-examples/config.json).

| Поле | Для чего |
|---|---|
| `amount.min`, `amount.step`, `amount.max_by_legal_form.{IP,OOO}`, `amount.default` | слайдер суммы. Максимум зависит от `company.legal_form` (он же лежит в `company.max_amount`) |
| `term.min`, `term.max`, `term.step`, `term.default` | слайдер срока |
| `rating.bands[]` | `{from, to, code: LOW/MEDIUM/HIGH, label, base_rate}` — подписи шкалы рейтинга |
| `products[]` | `{product_id, card_title, name, description}` — **ровно две карточки** экрана 5 |
| `borrowing_modes[]` | `{borrowing_mode, button_label, name}`. `button_label` для кнопок экрана 3, `name` для заголовков и сводки |
| `legal_forms[]` | `{legal_form, label, registration_label, registration_length}` — форма «Добавить бизнес» |
| `statuses[]`, `stages[]` | подписи статусов и шагов шкалы |
| `profile_fields[]` | поля анкеты (экран 8): `key`, `label`, `label_refinance` (подпись при рефинансировании), `type`, `unit`, `hint` |
| `texts.*` | готовые тексты: подпись источника рейтинга, подсказка «Что означает рейтинг?», «Рейтинг пока недоступен», пометки о предварительных условиях |

Названия «Оборотный кредит», «Кредит на оборудование», «Рефинансирование действующего кредита» и коды `NEW_CREDIT / REFINANCE / WORKING_CAPITAL / EQUIPMENT` используются **без переименований** (§15).

---

## 4. Маршруты и восстановление состояния

Рекомендуемые URL фронта (id компании и заявки всегда в URL, тогда обновление страницы ничего не теряет):

```
/login
/companies                                   — экран 1
/companies/:companyId                        — дашборд (экран 2)
/companies/:companyId/new                    — выбор способа займа (экран 3)
/applications/:appId/parameters              — сумма и срок (4)
/applications/:appId/product                 — цель и продукт (5)
/applications/:appId/refinance-loan          — выбор кредита (6)
/applications/:appId/refinance-params        — новые параметры (7)
/applications/:appId/business                — анкета (8)
/applications/:appId/checks                  — что проверит банк (9)
/applications/:appId/review                  — проверка перед отправкой (10)
/applications/:appId                         — статус / запрос сведений / решение / завершение (11–14)
/companies/:companyId/applications           — «Мои заявки»
/staff, /staff/applications/:appId           — панель сотрудника
```

- **Текущий шаг черновика** хранится на сервере в `current_step` (свободная строка до 50 символов). Отправляйте `current_step` в каждом `PATCH`. Значения: `parameters`, `product`, `refinance_loan`, `refinance_params`, `business`, `checks`, `review`. Когда клиент возвращается к черновику с дашборда, ведите его на `current_step`. После отправки сервер сбрасывает поле в `null`.
- **Выбранная компания** определяется `companyId` из URL. Последнюю выбранную можно запомнить в `localStorage` для удобства, но источником данных всегда остаётся сервер.
- Черновик сохраняется на сервере после каждого шага (§15). Локальное состояние — только кэш.

---

## 5. Экраны клиента

### Экран 1. Выбор бизнеса (§1)

| Действие | Запрос |
|---|---|
| Приветствие «{first_name}, здравствуйте!» | `GET /api/auth/me` → `user.first_name` |
| Список компаний | `GET /api/companies` → `items[]`: `{id, name, legal_form, legal_form_label, registration_number, registration_label, max_amount}`. Строка: `name` + `registration_label` + `registration_number` |
| «Добавить новый бизнес» (модалка) | `POST /api/companies` `{"legal_form": "IP"|"OOO", "name": "...", "registration_number": "..."}` → `201` и объект компании |

- Пустой список → «Пока нет добавленных бизнесов» и кнопка «Добавить новый бизнес».
- Одна компания → выбрана заранее.
- После создания компании добавьте её в список и выберите. Новая компания получает рейтинг 600 и не имеет кредитов.
- Ошибки модалки: `fields.name`, `fields.registration_number` (текст вида «ОГРНИП должен содержать 15 цифр»), `409 DUPLICATE_COMPANY`. **Модалку не закрывать, введённое не стирать.** Длину поля подсказывайте из `config.legal_forms[].registration_length`.
- Кнопка «Продолжить» неактивна, пока компания не выбрана, и показывает выбранную компанию в тексте или рядом.

Примеры: [`companies_list.json`](api-examples/companies_list.json), [`company_create_error.json`](api-examples/company_create_error.json).

### Экран 2. Дашборд компании (§2)

`GET /api/companies/{companyId}/dashboard` возвращает всё одним запросом ([`dashboard_ip.json`](api-examples/dashboard_ip.json)):

| Поле | Что показать |
|---|---|
| `company` | название, `registration_label` + `registration_number` |
| `client.full_name` | ФИО клиента |
| `rating` | `score` из `max`, `band_label` (низкий / средний / высокий), `source_label`, `updated_at`, `hint` для «Что означает рейтинг?». **`rating = null`** → показать `rating_unavailable_text` |
| `loans[]` | `name`, `original_amount`, `balance`, `rate`, `next_payment_date`, `next_payment_amount`. Пустой массив → «Действующих кредитов нет» |
| `active_applications[]` | ссылка «Текущая заявка» (номер, статус). У `DRAFT` номера нет: показывайте «Черновик» и ведите на `current_step` |
| `past_applications[]` | «Прошлые обращения» (`REJECTED`, `COMPLETED`) |
| `news[]` | лента из 6 карточек `{id, tag, title, summary}`, **уже отсортированная сервером** |

- Главная кнопка «Взять новый кредит» ведёт на экран 3.
- Клик по новости → `GET /api/news/{id}` → `{title, body}`, показать в модальном окне (абзацы в `body` разделены `\n\n`).
- Порядок новостей: сначала по цели активного черновика нового кредита, потом по правовой форме компании, потом общие. При смене компании или выбранной цели перезапросите дашборд, и порядок изменится.
- Завершённая заявка **не** появляется в `loans` (выдача денег не моделируется).

### Экран 3. Выбор способа займа (§3)

Две кнопки из `config.borrowing_modes[].button_label`. По нажатию:

```
POST /api/companies/{companyId}/applications  {"borrowing_mode": "NEW_CREDIT" | "REFINANCE"}
```

| Ответ | Что делать |
|---|---|
| `201` | создан новый черновик → `/applications/{id}/parameters` (или `/refinance-loan`) |
| `200` | уже есть активная заявка этого способа. Если `status == "DRAFT"`, продолжить с `current_step`, иначе открыть `/applications/{id}` (статус) |
| `409 NO_LOANS_TO_REFINANCE` | показать «У этой компании нет действующих кредитов для рефинансирования» и кнопку «Оформить новый кредит» (тот же запрос с `NEW_CREDIT`) |

У компании может быть одновременно **одна** активная заявка на новый кредит и **одна** на рефинансирование. Пример ответа: [`refinance_no_loans_409.json`](api-examples/refinance_no_loans_409.json).

Это правило держит и база — частичным уникальным индексом по активным статусам. Поэтому два одновременных запроса (две вкладки, двойной клик) не создают двух черновиков: второй получает `200` с той же заявкой.

### Экран 4. Новый кредит: сумма и срок (§4)

Черновик создаётся с `amount = 1 000 000` (у ИП не больше лимита) и `term_months = 12`, предварительный расчёт уже посчитан ([`draft_created.json`](api-examples/draft_created.json)).

- Слайдеры: `min`, `step` и `max` берутся из `config` и `company.max_amount`. Рядом поля точного ввода и подписи минимума и максимума.
- При изменении (с debounce ~300 мс) отправляйте:
  ```
  PATCH /api/applications/{id}  {"amount": 1500000, "term_months": 24, "current_step": "parameters"}
  ```
  Ответ — полная заявка с пересчитанными `preliminary_rate`, `preliminary_payment`. **Показывайте именно их**: расчёт делает сервер.
- Если вам нужен расчёт без сохранения, используйте `POST /api/pricing/quote` `{company_id, borrowing_mode, amount, term_months}` ([`quote_new.json`](api-examples/quote_new.json)). Для экрана 4 удобнее сразу PATCH: значения на экране и в черновике тогда гарантированно совпадают.
- Подписи:
  - «Предварительная ставка: {preliminary_rate} % годовых»;
  - если `rating_based == false`, добавить `rating_note` («расчёт без рейтинга»);
  - пометка `preliminary_note`.
- Ошибки: `fields.amount` (лимит или кратность 50 000), `fields.term_months`.
- «Продолжить» → экран 5.

### Экран 5. Цель и продукт (§5)

- Ровно две карточки из `config.products`: заголовок `card_title`, строка «Продукт: {name}», `description`.
- Выбор отправляет `PATCH {"product_id": "EQUIPMENT", "current_step": "product"}`. Сумма и срок **не сбрасываются**.
- Под карточками: `product_name`, `amount`, `term_months`, `preliminary_rate` и ссылка «Изменить сумму и срок» на экран 4.
- «Продолжить» без выбранного продукта не пускать: на отправке сервер всё равно вернёт `fields.product_id`.

### Экран 6. Рефинансирование: выбор кредита (§6)

- `GET /api/companies/{companyId}/loans` → `items[]`: поля как в дашборде плюс `active_application_id`. Если там не `null`, по кредиту уже есть заявка: карточку показать неактивной.
- Выбор: `PATCH {"existing_loan_id": 5, "current_step": "refinance_loan"}`. Сервер ставит `amount = balance` и пересчитывает условия.
- После выбора текст «Мы рассчитаем предварительные условия по выбранному кредиту».
- Ошибки:
  - `404` — кредит чужой или не существует;
  - `409 LOAN_ALREADY_IN_APPLICATION`.
- Заголовок сценария на всех следующих экранах — `borrowing_mode_label` («Рефинансирование действующего кредита»).

### Экран 7. Рефинансирование: новые параметры (§7)

- Блок «Сейчас» из `existing_loan`: `balance`, `rate`, `next_payment_amount`, `next_payment_date`.
- Слайдер срока 6–36: `PATCH {"term_months": 18, "current_step": "refinance_params"}`.
- **Сумма не редактируется**, это `amount` (= остаток). Попытка PATCH `amount` → 422.
- Сравнение берите из `comparison` в ответе заявки ([`refinance_draft.json`](api-examples/refinance_draft.json)):

| Поле | Значение |
|---|---|
| `current_rate` / `new_rate` | ставка сейчас / предварительно после рефинансирования |
| `current_next_payment` / `new_payment` | ближайший платёж сейчас / новый платёж |
| `rate_is_lower`, `payment_is_lower` | для подсветки |
| `is_better` | `false` → честно показать, что предложение не лучше текущего, и дать вернуться |
| `note` | пояснение, что оставшийся срок старого кредита может отличаться |

Экономию не обещать, если `is_better == false`.

### Экран 8. Анкета бизнеса (§8)

- Шапка: `company.name`, `company.legal_form_label`, `company.registration_label` + `registration_number`. Поля только для чтения. Ссылка на изменение реквизитов ведёт в карточку компании (в MVP просто на экран 1).
- Поля из `config.profile_fields`. Для `purpose_details` при `borrowing_mode == "REFINANCE"` используйте `label_refinance` («Почему хотите изменить условия?»).
- Сохранение: `PATCH {"business_profile": {"industry": "...", "months_operating": 36, "monthly_revenue": 1800000, "monthly_debt_payments": 120000, "purpose_details": "..."}, "current_step": "business"}`. Можно отправлять частично, сервер мержит.
- Числа показывайте с пробелами разрядов, а отправляйте **числами** (`1800000`, не `"1 800 000"`).
- Ошибки: `fields["business_profile.monthly_revenue"]` и т. п.
- Кнопки:
  - «Назад»;
  - «Сохранить и выйти» — тот же PATCH, затем переход на дашборд;
  - «Продолжить» — PATCH, затем экран 9.

### Экран 9. Что проверит банк (§9)

Статичный экран, запросов нет (только `PATCH {"current_step": "checks"}`). Тексты:
- проверяем регистрацию бизнеса (симулятор реестра);
- демонстрационную кредитную историю (симулятор бюро);
- полноту анкеты.

Реальные ФНС и бюро не запрашиваются. **Кнопок загрузки документов нет.**

### Экран 10. Проверьте заявку (§10)

- Данные: `GET /api/applications/{id}`, поля `company`, `borrowing_mode_label`, `product_name` или `existing_loan`, `amount`, `term_months`, `preliminary_rate`, `preliminary_payment`, `business_profile`.
- Под ставкой текст `config.texts.final_terms_note`.
- «Изменить» у каждого блока ведёт на нужный экран с `?return=review`, после сохранения возвращает обратно.
- Чекбокс «Подтверждаю достоверность синтетических данных и согласие на демонстрационную обработку».
- «Отправить заявку»:
  ```
  POST /api/applications/{id}/submit  {"confirm_data": true}
  ```
  - На время запроса кнопку заблокировать и показать индикатор. Двойной клик безопасен: второй запрос получит `409 ALREADY_SUBMITTED`.
  - `200` → перейти на `/applications/{id}`. Ответ — заявка с `number` вида `D-2026-000001` ([`application_submitted.json`](api-examples/application_submitted.json)).
  - `422` → остаться на сводке и подсветить блоки по ключам `fields` (`product_id`, `existing_loan_id`, `term_months`, `business_profile.*`, `confirm_data`).

### Экраны 11–14. Страница заявки

Один экран, который рисуется по `status`. Источник — `GET /api/applications/{id}`. Запрашивать при открытии и по кнопке «Обновить статус» (автоопроса нет).

**Общая часть для всех статусов:**

| Поле | Что показать |
|---|---|
| `number`, `company.name`, `submitted_at` | шапка |
| `status_label` | статус обычным языком |
| `stage.steps[]` | шкала из 4 шагов, у каждого `state`: `done` / `active` / `pending`. **Активный шаг вычисляет сервер, не подделывать прогресс** |
| `next_steps_text` | блок «Что дальше» |
| `events[]` | история: `created_at`, `label`, `actor` (для сотрудника приходит «Банк»), `text` (вопрос, ответ, комментарий), `fields` |
| `available_actions[]` | какие кнопки показывать (см. таблицу ниже) |

Кнопка «На главную» ведёт на `/companies/{company_id}`.

| `status` | Экран | `available_actions` | Что показывать |
|---|---|---|---|
| `IN_REVIEW` | 11 | `[]` | «Проверяем данные…» |
| `NEED_INFO` | 12 | `["info_response"]` | `info_request` + форма ответа |
| `APPROVED` | 13 | `["accept"]` | `decision`, кнопка «Принять условия» |
| `COUNTER_OFFER` | 13 | `["accept", "supplement"]` | сравнение «запрошено / предложено», «Принять новые условия» и «Вернуться к заявке» |
| `REJECTED` | 13 | `[]` | `decision.reason_text` (+ `decision.comment`), кнопка «На главную» |
| `COMPLETED` | 14 | `[]` | «Условия приняты», итоговые параметры |

#### Экран 12. «Нужно уточнить сведения» ([`application_need_info.json`](api-examples/application_need_info.json))

- Вверху заметный баннер «Нужно уточнить сведения».
- `info_request.message` — текст запроса сотрудника. `info_request.requested_fields[]` — `{key, label}`, поля анкеты, которые нужно заполнить (тип и единица из `config.profile_fields`).
- Форма: текстовое поле ответа (обязательно) и запрошенные поля (обязательны).
- Отправка:
  ```
  POST /api/applications/{id}/info-response
  {"answer_text": "Выручка выросла…", "fields": {"monthly_revenue": 2100000}}
  ```
  - `200` → статус `IN_REVIEW`, вопрос и ответ остаются в `events`.
  - `422` → ошибки в `fields.answer_text` или `fields["fields.monthly_revenue"]`.
  - Сервер проверяет анкету **целиком**, а не только спрошенные поля: если ответ оставит любое поле анкеты пустым, придёт `422` с ключами `fields.<ключ>`, а в заявке сохранится предыдущая корректная версия. Пустые значения в `fields` не отправляйте.
- `info_request` приходит **только** в статусе `NEED_INFO`. По старой ссылке после ответа он будет `null`, и форму показывать не нужно.

#### Экран 13. Решение ([`application_counter_offer.json`](api-examples/application_counter_offer.json), [`application_rejected.json`](api-examples/application_rejected.json))

`decision`:

| Поле | Значение |
|---|---|
| `kind` | `APPROVED` / `COUNTER_OFFER` / `REJECTED` |
| `amount`, `term_months`, `rate`, `monthly_payment` | **итоговые** условия банка. Ставку брать отсюда, а не из `preliminary_rate` |
| `comment` | пояснение банка |
| `requested.{amount, term_months, rate, monthly_payment}` | что запрашивал клиент, для сравнения |
| `changed_fields` | какие параметры изменились, для подсветки |
| `reason_text` | понятная причина отказа. Сырых кодов клиенту нет |
| `refinance_remainder`, `refinance_remainder_text` | если при рефинансировании банк предложил сумму меньше остатка: «Оставшуюся часть долга (X ₽) нужно погасить по текущему кредиту» |

- «Принять условия» → `POST /api/applications/{id}/accept`. Ответ: `status = COMPLETED`. Повтор → `409 ALREADY_ACCEPTED`. Блокируйте кнопку на время запроса.
- «Вернуться к заявке» (только `COUNTER_OFFER`) открывает форму дополнения: текст обязателен, любые поля анкеты по желанию.
  ```
  POST /api/applications/{id}/supplement  {"answer_text": "...", "fields": {"monthly_revenue": 3000000}}
  ```
  Предложение аннулируется, заявка возвращается в `IN_REVIEW`, сотрудник решает заново. Анкета и здесь проверяется целиком: при `422` предложение остаётся в силе, а прежние данные не меняются.
- Не писать «Деньги зачислены».

#### Экран 14. Завершение ([`application_completed.json`](api-examples/application_completed.json))

- Показать «Условия приняты», `decision.amount / term_months / rate / monthly_payment`, `number`, `completed_at`.
- Кнопки «На главную» и «Посмотреть историю заявки» (та же страница, блок `events`).
- Явно указать, что подписание и выдача денег в демонстрации не моделируются.

### «Мои заявки»

`GET /api/companies/{companyId}/applications` → `items[]`, краткий вид: `number`, `status_label`, `borrowing_mode_label`, `product_name` / `existing_loan_name`, `amount`, `term_months`, `created_at`, `submitted_at`, `current_step`. Пример: [`my_applications.json`](api-examples/my_applications.json).

### «Поддержка»

`GET /api/support` (без авторизации) → `items[]: {id, question, answer}`. Показывать в модалке или на странице справки. Пример: [`support.json`](api-examples/support.json).

### Новости

- `GET /api/news?company_id=&product_id=` → `items[]`, отсортированные по правилу §15 ([`news_list.json`](api-examples/news_list.json)).
- `GET /api/news/{id}` → полный текст ([`news_detail.json`](api-examples/news_detail.json)).

---

## 6. Панель сотрудника

Вход тем же `POST /api/auth/login` (логин `staff`). По `user.role == "EMPLOYEE"` открывайте `/staff`. Черновики сотруднику не видны.

### Очередь: `GET /api/staff/applications`

- Параметры:
  - `status` можно передать несколько раз (`?status=IN_REVIEW&status=NEED_INFO`);
  - `q` ищет по номеру или названию компании.
- Ответ ([`staff_queue.json`](api-examples/staff_queue.json)):
  - `items[]` — краткий вид заявки + `client_name` + `preliminary_rate`;
  - `counts` — количество заявок по статусам, для чипов фильтра.
- Фильтры из дизайна: «Все» (без `status`), «На рассмотрении» (`status=IN_REVIEW`).

### Карточка: `GET /api/staff/applications/{id}` ([`staff_card.json`](api-examples/staff_card.json))

Всё, что видит клиент, плюс:

| Поле | Что показать |
|---|---|
| `client.full_name` | ФИО клиента |
| `rating` | рейтинг бюро или `null` |
| `checks[]` | `{key, label, status: OK/WARN/FAIL/UNAVAILABLE, details}`: регистрация, кредитная история, полнота анкеты, долговая нагрузка |
| `scoring` | `{bureau_score, debt_load_pct, recommendation: APPROVE/REJECT/MANUAL, recommendation_label, reasons[]}` — **только для сотрудника** |
| `info_requests[]` | все запросы и ответы клиента (`answer_text`, `answer_fields`) |
| `decisions[]` | все решения, `is_active` |
| `staff_actions[]` | доступные действия. Непустой только в `IN_REVIEW` |
| `events[].actor` | здесь настоящие имена сотрудников |

### Решения (все только из `IN_REVIEW`; иначе `409 INVALID_STATUS`)

| Действие | Запрос | Правила |
|---|---|---|
| Запросить сведения | `POST …/request-info` `{"message": "...", "requested_fields": ["monthly_revenue"]}` | `requested_fields` ⊂ ключей `config.profile_fields`, может быть пустым |
| Одобрить | `POST …/approve` `{"comment": "..."}` | `comment` обязателен и непустой. Подтверждает **ровно запрошенные** параметры и предварительную ставку |
| Другие условия | `POST …/counter-offer` `{"amount": 1200000, "term_months": 24, "rate": 19.5, "comment": "причина"}` | `comment` обязателен. Лимиты как у клиента. Для рефинансирования сумма от 100 000 ₽ до остатка долга. Если всё совпадает с запрошенным → `422 SAME_AS_REQUESTED` («используйте Одобрить») |
| Отказать | `POST …/reject` `{"reason_code": "LOW_RATING", "comment": "..."}` | коды из `GET /api/staff/reject-reasons` ([`staff_reject_reasons.json`](api-examples/staff_reject_reasons.json)) |

- Положительное решение (одобрение и другие условия) сервер пропускает только по полной анкете: иначе `422 VALIDATION_ERROR` с ключами `business_profile.<ключ>` и подсказкой запросить сведения у клиента. Отказ по неполной анкете возможен — для этого и есть причина `INSUFFICIENT_DATA`.
- Ответ любого действия — обновлённая карточка.
- Платёж по встречному предложению считает сервер, его можно сразу показать.
- Перед отправкой в дизайне есть экран «Подтверждение решения», это чисто фронтовый шаг.

---

## 7. Демо-сценарий для защиты (≈5 минут)

1. `POST /api/demo/reset`.
2. **alexey** выбирает «ИП Морозов». Дашборд: рейтинг 820 (высокий), оборотный кредит с остатком 600 000 ₽, первая новость про ИП.
3. Переключается на «Маяк Трейд»: рейтинг 620, «Действующих кредитов нет», первая новость про ООО. Возвращается к ИП.
4. «Взять новый кредит» → «Новый кредит» → сумма 1 500 000 ₽, срок 24 → ставка 18 %. Срок 25 → ставка 20 %.
5. Выбор «Покупка оборудования». Сумма и срок сохранились. На дашборде первая новость теперь про оборудование.
6. Анкета → «Что проверит банк» → сводка → отправка. Получен номер `D-2026-…`, шаг «Проверка данных».
7. **staff** видит заявку в очереди и рекомендацию «Одобрить», запрашивает выручку.
8. **alexey** видит «Нужно уточнить сведения» и отвечает.
9. **staff** делает встречное предложение: 1 200 000 ₽, 19,5 %.
10. **alexey** видит сравнение запрошенного и предложенного, принимает. Экран «Условия приняты». Кредит не появился в действующих, заявка — в прошлых обращениях.
11. Бонус:
    - рефинансирование «Вектор-Станок» на 30 мес.: ставка 28 % против текущих 23 %, честно показано `is_better=false`, затем отказ с понятной причиной;
    - `POST /api/demo/bureau {"available": false}` → «Рейтинг пока недоступен», ставка 24 % «расчёт без рейтинга».
12. **maria** не видит компаний Алексея.

---

## 8. Индекс примеров `docs/api-examples/`

| Файл | Что внутри |
|---|---|
| `auth_login` | ответ логина |
| `config` | справочники |
| `companies_list`, `company_create_error` | экран 1 |
| `dashboard_ip`, `loans_ip` | экран 2 и 6 |
| `quote_new`, `quote_refinance` | расчёт без сохранения |
| `draft_created`, `draft_filled`, `draft_patch_error` | экраны 4–8 |
| `refinance_draft`, `refinance_no_loans_409` | экраны 6–7 |
| `submit_incomplete_422`, `application_submitted`, `submit_again_409` | экран 10 |
| `application_need_info` | экран 12 |
| `application_counter_offer`, `application_rejected` | экран 13 |
| `application_completed`, `accept_again_409` | экран 14 |
| `my_applications` | «Мои заявки» |
| `news_list`, `news_detail`, `support` | контент |
| `staff_queue`, `staff_card`, `staff_reject_reasons` | панель сотрудника |
| `unauthorized_401` | ошибка авторизации |
