"""Административный сброс демонстрационных данных.

Публичные ручки /api/demo/* по умолчанию выключены (DEMO_TOOLS_ENABLED=false):
они не требуют авторизации, поэтому на общем сервере их держать нельзя. Сброс
остаётся доступен тому, у кого есть доступ к серверу, — этой командой.

База берётся из того же DATABASE_URL, что и у приложения. Команда пересоздаёт
таблицы и возвращает исходные демо-данные: всё, что накопили клиенты и
сотрудники, будет удалено. Поэтому нужен явный флаг --yes.

Запуск (в контейнере API):
    docker compose exec api python scripts/demo_reset.py --yes
Запуск локально:
    python scripts/demo_reset.py --yes
"""

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.settings import settings  # noqa: E402
from app.seed import init_db  # noqa: E402
from app.simulators import bureau  # noqa: E402
from app.staff_pipeline.seed import seed_department_on_startup  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Пересоздать демонстрационные данные «Дела».")
    parser.add_argument("--yes", action="store_true",
                        help="подтверждение: текущие заявки и история будут удалены")
    args = parser.parse_args()

    print(f"База: {settings.database_url}")
    if not args.yes:
        print("Ничего не изменено. Повторите с --yes, если действительно нужен сброс.")
        return 1

    init_db(reset=True)
    counts = seed_department_on_startup()
    bureau.set_available(settings.bureau_available)
    print(f"Готово: демо-данные пересозданы, отдел сотрудников восстановлен ({counts}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
