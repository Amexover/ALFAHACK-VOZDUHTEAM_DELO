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
