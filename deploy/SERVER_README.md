# Текущий сервер «Дело»

Сайт: http://195.133.41.30. Swagger: http://195.133.41.30/docs.

## Расположение

- /opt/delo/frontend — активный frontend, исходники и dist.
- /opt/delo/backend — существующий backend; рабочая .env в /opt/delo/.env сохранена.
- /opt/delo/delivery — полный комплект для команды: frontend, backend, единый Compose для чистого запуска, документы и тесты. Это отдельный способ запуска, а не замена текущего Compose VPS.
- /opt/delo/reports — отчёт, матрица требований методички, RELEASE.json и снимки.
- /opt/delo/releases — архив исходников и SHA-256.

## Команды активного стенда

```sh
cd /opt/delo
docker compose -f docker-compose.yml -f deploy/compose.frontend.yml ps
docker compose -f docker-compose.yml -f deploy/compose.frontend.yml build frontend
docker compose -f docker-compose.yml -f deploy/compose.frontend.yml up -d --no-build --no-deps frontend
```

Порт 80 обслуживает nginx. /api идёт во внутренний API; его прямой порт ограничен 127.0.0.1:8000. PostgreSQL наружу не опубликован. Старый README.md описывает исходный backend без frontend: для активного стенда нужны оба Compose-файла, как выше.

Не запускать корневой backend Compose отдельно без учёта работающего frontend. Не удалять рабочий pgdata volume. Сброс общей БД не выполнялся; тестовые полноценные сценарии проверялись в отдельном проекте delo-acceptance. Его контейнеры и сеть после проверки удалены, тестовый volume сохранён. Локальный комплект в delivery по умолчанию отключает demo reset, существующая .env VPS не изменялась.

Остались вопросы backend и финальной сдачи — см. reports/FRONTEND_REPORT.md и reports/METHOD_COMPLIANCE.md. GitHub отложен пользователем до обсуждения; ничего туда не отправлялось.

## Служебные демо-операции: сброс базы и симулятор бюро

`POST /api/demo/reset` и `POST /api/demo/bureau` не требуют авторизации. В коде они
теперь выключены по умолчанию (`DEMO_TOOLS_ENABLED=false`), и при выключенном флаге
обе ручки отвечают `404 NOT_FOUND` — вызвать их напрямую нельзя.

На рабочем сервере проверить и закрыть:

```sh
cd /opt/delo
grep -n DEMO_TOOLS_ENABLED .env || echo "DEMO_TOOLS_ENABLED=false" >> .env
sed -i "s/^DEMO_TOOLS_ENABLED=.*/DEMO_TOOLS_ENABLED=false/" .env
docker compose -f docker-compose.yml -f deploy/compose.frontend.yml up -d --no-build --no-deps api
curl -s -o /dev/null -w "%{http_code}
" -X POST http://127.0.0.1:8000/api/demo/reset   # ожидаем 404
```

Пересоздание нужно потому, что переменные окружения контейнер получает только при
создании: `restart` старую настройку сохранит. Том `pgdata` не затрагивается, заявки
остаются на месте.

Сброс демо-данных остаётся доступен тому, у кого есть доступ к серверу:

```sh
docker compose -f docker-compose.yml -f deploy/compose.frontend.yml exec api python scripts/demo_reset.py --yes
```

Без `--yes` команда ничего не делает и только печатает адрес базы. Для показа, где
сброс нужен кнопкой, поднимается отдельный стенд с `DEMO_TOOLS_ENABLED=true` — на
общем сервере этот флаг включать нельзя.
