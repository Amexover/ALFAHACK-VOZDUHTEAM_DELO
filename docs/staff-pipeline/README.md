# Отдел сотрудников банка — рабочие документы

Углубление существующего модуля сотрудника до полноценного кредитного конвейера.
Ветка `feat/staff-pipeline`. План работ — `ПЛАН_РАБОТ_отдел_сотрудников.md` (вне репозитория).

Сделано: тикеты 01–04 — фундамент, конвейер, скоринг со снимками и обратимый автоотказ.
Приёмка и сведения о выпуске: [TICKET_04_ACCEPTANCE.md](TICKET_04_ACCEPTANCE.md).

| Документ | О чём |
|---|---|
| [API_CONTRACT.md](API_CONTRACT.md) | контракт всех ручек отдела, включая будущие — по нему фронтендер рисует экраны |
| [PIPELINE.md](PIPELINE.md) | как устроен конвейер: два слоя состояний, сроки, права, врезка в чужие ручки |
| [SCORING.md](SCORING.md) | правила, пороги, снимки и предварительный пересчёт |
| [AUTO_REJECT.md](AUTO_REJECT.md) | политика приёма, отмена и границы автоматизации |
| [TICKET_04_ACCEPTANCE.md](TICKET_04_ACCEPTANCE.md) | итоговая приёмка, сервер и идентификатор версии |
| [MIGRATIONS.md](MIGRATIONS.md) | как раскатываются изменения схемы на заполненную базу |
| [MESSAGE_TO_TEAMMATE.md](MESSAGE_TO_TEAMMATE.md) | что отправлено второму разработчику: список тронутых файлов и гарантии |
| [TICKET_01_ACCEPTANCE.md](TICKET_01_ACCEPTANCE.md) | приёмка тикета 01 по пунктам |
| [TICKET_02_ACCEPTANCE.md](TICKET_02_ACCEPTANCE.md) | приёмка тикета 02 по пунктам |
| [TICKET_03_ACCEPTANCE.md](TICKET_03_ACCEPTANCE.md) | приёмка тикета 03 по пунктам |

## Записанные прогоны

| Файл | Что в нём |
|---|---|
| [BASELINE_TESTS.txt](BASELINE_TESTS.txt) | тесты второго разработчика до начала работ — 32 зелёных |
| [TESTS_AFTER_TICKET_01.txt](TESTS_AFTER_TICKET_01.txt) | все тесты после тикета 01 — 44 зелёных |
| [TESTS_AFTER_TICKET_02.txt](TESTS_AFTER_TICKET_02.txt) | все тесты после тикета 02 — 68 зелёных |
| [TESTS_AFTER_TICKET_03.txt](TESTS_AFTER_TICKET_03.txt) | полный прогон после тикета 03 |
| [TESTS_AFTER_TICKET_04.txt](TESTS_AFTER_TICKET_04.txt) | 186 тестов, включая 20 проверок автоматического контура |
| [TESTS_CONTAINER_TICKET_04.txt](TESTS_CONTAINER_TICKET_04.txt) | те же 186 тестов в Linux-образе |
| [POSTMAN_TICKET_04.txt](POSTMAN_TICKET_04.txt) | 46 запросов, 50 проверок, 0 ошибок |
| [CONCURRENCY_TICKET_04.json](CONCURRENCY_TICKET_04.json) | конкурентные приём, отмена и решения на PostgreSQL |
| [DEPLOY_TICKET_04.txt](DEPLOY_TICKET_04.txt) | миграция и переключение рабочего VPS с проверкой старых строк |
| [CLIENT_CONTRACT_CHECK.txt](CLIENT_CONTRACT_CHECK.txt) | 29 записанных примеров ответов пересобраны на текущем коде: состав полей не изменился |
| [OPENAPI_CHECK.txt](OPENAPI_CHECK.txt) | 27 существующих ручек и 19 схем описаны ровно как раньше |
| [STAFF_SIGNATURES_CHECK.txt](STAFF_SIGNATURES_CHECK.txt) | в файле чужих ручек изменены только сигнатуры, тела функций совпадают дословно |
| [MIGRATION_CHECK.txt](MIGRATION_CHECK.txt) | миграция на заполненной базе, повторный запуск и откат |
| [SMOKE_TICKET_01.txt](SMOKE_TICKET_01.txt) | прогон руками на живом сервере: роли и очередь |
| [SMOKE_TICKET_02.txt](SMOKE_TICKET_02.txt) | прогон руками на живом сервере: весь конвейер от очереди до решения |

Примеры ответов: [docs/api-examples/department/](../api-examples/department/) — снятые с живого
приложения; [planned/](../api-examples/department/planned/) — исторические эскизы.
Для интеграции используйте файлы из основного каталога примеров.

## Код отдела

```
backend/app/staff_pipeline/
    enums.py      роли внутри отдела, этапы, действия, типы внутренних событий, нормативы
    models.py     4 таблицы отдела и запрет правок истории; существующие таблицы не меняются
    security.py   сотрудник отдела: роль и режим правил, зависимости поверх staff_user
    rules.py      права: одно место на все проверки этапа и исполнителя
    pipeline.py   приём в конвейер, сверка со статусом, сроки, переходы, история
    scoring.py    декларативные правила, сбор фактов, расчёт и снимки оценки
    auto_policy.py отдельная узкая политика приёма банка
    deps.py       врезки в существующие ручки сотрудника — только сигнатуры
    views.py      представления отдела
    api.py        ручки отдела (префикс /api/staff)
    schemas.py    тела запросов ручек отдела
    seed.py       свой идемпотентный сид: сотрудники отдела и демонстрационная очередь
backend/migrations/                   одна ревизия 20261022_01
backend/tests/test_department.py      тесты тикета 01 (12)
backend/tests/test_pipeline.py        тесты тикета 02 (24)
backend/tests/test_scoring.py         тесты тикета 03 (90)
backend/tests/test_auto_reject.py     тесты тикета 04 (20)
backend/tests/test_review_fixes.py    регрессии из ревью (8 проверок)
backend/scripts/check_migration.py              миграция на заполненной базе
backend/scripts/check_client_contract.py        клиентские ответы не изменились
backend/scripts/check_openapi_contract.py       описание существующих ручек не изменилось
backend/scripts/check_staff_file_untouched.py   в чужом файле правлены только сигнатуры
backend/scripts/gen_department_examples.py      пересборка примеров ответов отдела
```

В рамках тикетов в чужих файлах изменено 11 строк: 7 в `backend/app/api/staff.py` (вставленный импорт и
6 правок сигнатур), 3 вставленные строки в `backend/app/main.py`, 1 строка в
`backend/requirements.txt`. Тела функций в `staff.py` не тронуты. Исправления ревью
дополнительно затрагивают `backend/app/api/meta.py` (сид отдела при сбросе демобазы)
и `backend/Dockerfile` (копирование файлов миграций).

## Команды

```bash
cd backend
python -m pytest -q -p no:cacheprovider          # 186 тестов
python scripts/check_migration.py                # миграция на заполненной базе
python scripts/check_client_contract.py          # клиентский контракт не изменился
python scripts/check_openapi_contract.py         # описание существующих ручек не изменилось
python scripts/check_staff_file_untouched.py     # в чужом файле только сигнатуры
python -m scripts.gen_department_examples        # пересобрать примеры ответов
alembic -c alembic.ini upgrade head              # применить миграции
DEPARTMENT_DEMO_QUEUE=false python -m uvicorn app.main:app   # старт без демо-очереди
```

Если включены служебные демо-ручки (`DEMO_TOOLS_ENABLED=true`), `POST /api/demo/reset`
восстанавливает и исходный сид, и сотрудников отдела с их ролями. Демо-очередь отдела
восстанавливается по тому же флагу `DEPARTMENT_DEMO_QUEUE`, что и при запуске приложения.

После исправлений ревью добавлены 8 регрессионных проверок: блокировка до проверки прав
для четырёх действий, отложенное чтение ответа клиента на двух этапах и повторный сброс
демобазы с включённой и выключенной очередью. Протоколы приёмки выше сохраняют исходные
результаты тикетов до этих исправлений.

Историческая проверка после исправлений Т2: 76 тестов прошли на SQLite в памяти, контракт OpenAPI
(27 существующих путей и 19 схем) и тела функций `staff.py` совпали с HEAD. Миграция
проверена на заполненной прежней схеме, при повторном запуске, откате и после `create_all`.
Наличие файлов Alembic в инструкциях Docker COPY проверено. Последующие сборка обоих
образов, полный прогон, коллекция и конкуренция на PostgreSQL выполнены в Т4;
актуальные результаты находятся в [TICKET_04_ACCEPTANCE.md](TICKET_04_ACCEPTANCE.md).
