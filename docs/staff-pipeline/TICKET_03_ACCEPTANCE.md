# Тикет 03 — приёмка

Дата: 22 октября 2026. Ветка: `feat/staff-pipeline`.
Реализация: `backend/app/staff_pipeline/scoring.py`, интеграция в модуле отдела.
Контракт и примеры: [API_CONTRACT.md](API_CONTRACT.md),
[SCORING.md](SCORING.md), [JSON](../api-examples/department/scoring_card.json).

| Пункт плана | Подтверждение |
|---|---|
| Тесты второго разработчика зелёные | Полный прогон включает все 32 исходных теста без изменений |
| Старые поля оценки сохранены | `test_legacy_scoring_block_of_the_staff_card_did_not_change`; сверка 29 примеров API |
| Разбор каждого правила | `/scoring`: формулировка, `fired`, вклад и объяснение; `test_scoring_card_explains_every_rule_and_names_the_ruleset_version` |
| Версия набора | `ruleset_version: RS-2026.10.1` в оценке, снимке и событии решения |
| Все пять факторов | Рейтинг, нагрузка, срок бизнеса, полнота анкеты, отношение суммы к выручке |
| Короткий срок и готовая причина | `test_short_working_history_lowers_the_score_and_suggests_a_ready_reason`, код `SHORT_HISTORY` |
| Снимки при приёме и решении | `test_snapshot_is_taken_on_intake_and_on_decision`, `test_all_decisions_freeze_the_evaluation` для всех трёх решений |
| Смена версии не меняет принятое решение | `test_a_new_ruleset_version_does_not_change_an_already_decided_application`; сохранены также подписи и факты |
| Рекомендация отделена от решения и скрыта от клиента | Тест одобрения при `REJECT`; 403 на служебные ручки; отсутствие оценки в клиентском ответе |
| Предварительный пересчёт не сохраняет изменения | `test_preview_leaves_the_stored_application_untouched`, `test_preview_before_intake_does_not_write_anything` |
| Правила описаны данными | `Rule` + `Band`; `test_a_new_rule_needs_no_change_in_the_calculation` |
| Границы каждого правила проверены | Параметризованные тесты всех полос и порогов срока бизнеса; интеграционные проверки без округления до сравнения |

Разбор для карточки отдаётся отдельной ручкой `/scoring`, как согласовано в тикете 01.
Прежний блок карточки не меняется; его рекомендация может отличаться от нового движка.
Новый фронтенд должен получать подробный разбор из `/scoring`.

Дополнительно проверены повторное решение после дополнения клиентом, сохранность старых
снимков, откат снимка при ошибке решения, запрет ORM на правку/удаление снимка,
идемпотентность приёма и ограничения суммы/срока, включая рефинансирование.

## Проверки

Команды выполняются из `backend` в существующей `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts/check_client_contract.py
.\.venv\Scripts\python.exe scripts/check_openapi_contract.py
.\.venv\Scripts\python.exe scripts/check_staff_file_untouched.py HEAD
.\.venv\Scripts\python.exe -m scripts.gen_department_examples
```

Полный прогон: **166 passed, 1 warning** (107,31 с). Предупреждение — устаревающий
алиас `BlockingPortal` в стороннем Starlette, без ошибок тестов.
Протокол: [TESTS_AFTER_TICKET_03.txt](TESTS_AFTER_TICKET_03.txt).
Отдельный прогон скоринга: **90 passed**. Сверка контрактов: все **29** примеров
сохранили структуру; **27** существующих путей OpenAPI и **19** схем совпали;
все **8** тел функций `app/api/staff.py` совпали с HEAD. В Т3 этот файл не менялся.
Примеры отдела пересобраны; успешные ответы — 200, ошибки скоринга — ожидаемые 403/422.

Прогоны выполнены с файловой SQLite-базой во временном каталоге. Ограничения песочницы
мешали SQLite открыть файл, поэтому использован разрешённый запуск вне песочницы.
Зависимости и исходные тесты для этого не менялись. PostgreSQL и VPS в этом тикете
не проверялись. Таблица снимков уже есть в миграции Т1; схема БД не менялась.
Общий `docs/openapi.json` не перегенерирован: по плану это финальный шаг Т4.
