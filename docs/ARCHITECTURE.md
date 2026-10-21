# Архитектура и границы MVP

## Компоненты

```mermaid
flowchart LR
  Client[Клиент: React] --> Web[nginx: веб-интерфейс]
  Staff[Сотрудник: React] --> Web
  Web -->|/api, тот же origin| API[FastAPI]
  API --> DB[(PostgreSQL 16)]
  API --> Registry[Локальный симулятор реестра]
  API --> Bureau[Локальный симулятор бюро]
  DB --> Volume[Постоянный Docker volume]
```

Единое React-приложение с разделением по ролям. Сервер проверяет принадлежность данных и права, а не полагается на скрытые кнопки. httpOnly-cookie работает на одном origin: frontend не сохраняет токен в localStorage. localStorage содержит только последний выбранный ID компании, отдельно для каждого пользователя. Никаких CDN, внешних шрифтов или платных сервисов основному интерфейсу не нужно. Swagger backend использует внешние ассеты своей стандартной страницы; сама схема JSON доступна локально, а коллекция запросов находится в репозитории.

В /opt/delo на VPS сохранён исходный backend Compose. Для установки фронта к нему добавлен deploy/compose.frontend.yml: nginx получает порт 80, прямой порт API ограничен 127.0.0.1:8000. PostgreSQL не опубликован наружу. Корневой docker-compose.yml в этом комплекте запускает все три компонента из исходников на обычном ПК.

## Машина состояний

```mermaid
stateDiagram-v2
  [*] --> DRAFT
  DRAFT --> IN_REVIEW: отправка
  IN_REVIEW --> NEED_INFO: запрос сотрудника
  NEED_INFO --> IN_REVIEW: ответ клиента
  IN_REVIEW --> APPROVED: одобрение
  IN_REVIEW --> COUNTER_OFFER: другие условия
  IN_REVIEW --> REJECTED: отказ
  COUNTER_OFFER --> IN_REVIEW: дополнение, старое предложение аннулируется
  APPROVED --> COMPLETED: принятие
  COUNTER_OFFER --> COMPLETED: принятие
  COMPLETED --> [*]
  REJECTED --> [*]
```

COMPLETED означает принятие условий в демонстрации. Выдача денег не происходит, действующий кредит автоматически не добавляется.

## Модель данных

```mermaid
erDiagram
  users ||--o{ companies : owns
  companies ||--o| bureau_ratings : has
  companies ||--o{ existing_loans : has
  companies ||--o{ applications : submits
  existing_loans |o--o{ applications : refinanced_by
  applications ||--o{ application_events : records
  applications ||--o{ info_requests : receives
  applications ||--o{ decisions : receives
```

Поля таблиц, расчёты, каталог продуктов и контракты: BACKEND_PROJECT_MAP.md. Фактический DDL описан SQLAlchemy-моделями backend/app/models.py. Обновление анкеты после запроса сотрудника сохраняется в той же заявке; историю дополнений содержат info_requests и application_events. Отдельной неизменяемой версии всей исходной анкеты нет — ограничение текущего backend.

## Допущения

- Пользователи и компании синтетические; действует заранее созданная демонстрационная авторизация.
- Проверка реестра ограничена форматом номера. Данные бюро заранее подготовлены локально.
- Внутренняя оценка использует рейтинг и долговую нагрузку, а сотрудник отдельно принимает решение.
- Два кредитных продукта имеют одинаковые лимиты. Различаются назначением; это явно выбранное упрощение.
- Нет документов, электронной подписи, выдачи, платных API, LLM и фонового worker. До результата заявки путь связан внутри продукта; оформление после результата вынесено за границы версии.
- Один API-процесс, PostgreSQL volume и restart policy не равны промышленной отказоустойчивости. Миграции, бэкапы и многорепличная работа требуют отдельной доработки.
