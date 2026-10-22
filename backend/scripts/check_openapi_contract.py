"""Проверка, что описание существующих ручек не изменилось.

В репозитории лежит docs/openapi.json, выгруженный вторым разработчиком до наших
работ. Скрипт собирает описание API на текущем коде и сверяет каждую записанную
ручку с записанным описанием: параметры, тела запросов и схемы должны совпадать.

Наши ручки отдела в записанном файле отсутствуют — они только добавляются, и это
показано отдельной строкой. Сам docs/openapi.json не перезаписывается: по контракту
описание API перегенерируется один раз, последним шагом (тикет 04).

Запуск:  python scripts/check_openapi_contract.py
"""

import json
import os
import pathlib
import sys
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[1]
RECORDED = BACKEND.parent / "docs" / "openapi.json"

os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "spec.db"))
sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402


def main() -> int:
    recorded = json.loads(RECORDED.read_text(encoding="utf-8"))
    current = app.openapi()

    same, differ, missing = [], [], []
    for path, described in recorded["paths"].items():
        if path not in current["paths"]:
            missing.append(path)
        elif current["paths"][path] == described:
            same.append(path)
        else:
            differ.append(path)

    added = sorted(set(current["paths"]) - set(recorded["paths"]))
    print(f"записано ручек до наших работ: {len(recorded['paths'])}")
    print(f"описание совпадает: {len(same)}")
    print(f"пропали: {missing or '—'}")
    print(f"изменились: {differ or '—'}")
    print(f"добавлено наших ручек: {len(added)}")
    for path in added:
        print(f"  + {path}")

    recorded_schemas = recorded.get("components", {}).get("schemas", {})
    current_schemas = current.get("components", {}).get("schemas", {})
    changed_schemas = [name for name, body in recorded_schemas.items()
                       if current_schemas.get(name) != body]
    print(f"схем записано: {len(recorded_schemas)}, изменилось: {changed_schemas or '—'}")

    if differ or missing or changed_schemas:
        for path in differ:
            print(f"\n--- {path}")
            print(f"было:  {json.dumps(recorded['paths'][path], ensure_ascii=False)[:600]}")
            print(f"стало: {json.dumps(current['paths'][path], ensure_ascii=False)[:600]}")
        print("\nПРОВЕРКА НЕ ПРОЙДЕНА: описание существующих ручек изменилось.")
        return 1

    print("\nПРОВЕРКА ПРОЙДЕНА: существующие ручки описаны ровно как раньше, добавлены только наши.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
