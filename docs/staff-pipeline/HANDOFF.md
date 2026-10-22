# Передача владельцу репозитория

Публикацию на GitHub пользователь оставил владельцу. Оба настроенных способа доступа
используют `melekhinartem19-hue`; репозиторий `Amexover/ALFAHACK-VOZDUHTEAM_DELO`
вернул 403 на пробную отправку. Настройки учётных записей и доступа не менялись.

Версия `delo-staff-2026-10-22-v1` уже работает на VPS. Локальная ветка `main`
включает `feat/staff-pipeline` без конфликтов. Удалённый `origin/main` оставлен владельцу.
Git bundle и архив исходников лежат рядом с каталогом `repo`:

- `delo-staff-2026-10-22-v1.bundle` — Git-история и ветки `main`, `feat/staff-pipeline`;
- `delo-staff-2026-10-22-v1.tar.gz` — исходники и документы без .git и окружений.

В текущей рабочей копии после проверки владельцу достаточно отправить `main`:

```sh
git push origin main
```

В другой копии можно принять bundle:

```sh
git fetch /path/to/delo-staff-2026-10-22-v1.bundle main:staff-t4-delivery
git checkout main
git pull --ff-only origin main
git merge --ff-only staff-t4-delivery
git push origin main
```

База слияния: `ee2b3b5b1b6fa873a65fe37ddaba0e857c3e9ac1`. Если удалённый main уже
изменился, нужен обычный разбор слияния и повторный прогон тестов; force push не нужен.
Повторно выкатывать сервер ради публикации этих исходников не требуется.

Протокол: [TICKET_04_ACCEPTANCE.md](TICKET_04_ACCEPTANCE.md).
