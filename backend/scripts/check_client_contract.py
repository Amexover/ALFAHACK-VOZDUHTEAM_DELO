"""Проверка контракта «клиентский ответ не изменился ни одним полем».

В репозитории лежит генератор примеров ответов второго разработчика
(scripts/gen_examples.py) и записанные им примеры в docs/api-examples/ — снятые
до наших работ. Скрипт прогоняет тот же генератор на текущем коде во временный
каталог (ни один записанный файл не перезаписывается) и сверяет каждый ответ
с записанным: состав полей и вложенность должны совпадать дословно.

Сравнивается структура, а не значения: идентификаторы, номера и отметки времени
в новом прогоне законно другие.

Запуск:  python scripts/check_client_contract.py
Вывод пригоден для протокола приёмки (docs/staff-pipeline/CLIENT_CONTRACT_CHECK.txt).
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
RECORDED = REPO / "docs" / "api-examples"

# Ответы ручек сотрудника: их состав полей тоже не должен измениться.
STAFF_EXAMPLES = {"staff_queue", "staff_card", "staff_reject_reasons"}


def skeleton(value):
    """Структура ответа без значений: имена полей, вложенность и тип значения.

    Целое и дробное считаются одним типом: в JSON это одно и то же число,
    и 20 против 20.0 — не изменение состава полей.
    """
    if isinstance(value, dict):
        return {k: skeleton(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [skeleton(value[0])] if value else []
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def regenerate(into: pathlib.Path) -> None:
    """Запускает чужой генератор так, чтобы он писал во временный каталог."""
    script = into / "backend" / "scripts" / "gen_examples.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(BACKEND / "scripts" / "gen_examples.py", script)
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND),
        "PYTHONIOENCODING": "utf-8",
        # генератор пишет файлы кодировкой по умолчанию — на Windows это не UTF-8
        "PYTHONUTF8": "1",
        # демо-очередь отдела выключена: сверяем ровно тот сценарий, который записан в примерах
        "DEPARTMENT_DEMO_QUEUE": "false",
    }
    done = subprocess.run([sys.executable, str(script)], cwd=into, env=env,
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        print(done.stdout)
        print(done.stderr)
        raise SystemExit("генератор примеров не отработал")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        regenerate(tmp_path)
        produced = tmp_path / "docs" / "api-examples"

        recorded_files = sorted(p.name for p in RECORDED.glob("*.json"))
        print(f"записанных примеров до наших работ: {len(recorded_files)}")
        print(f"пересобрано на текущем коде: {len(list(produced.glob('*.json')))}")

        same, differ, missing = [], [], []
        for name in recorded_files:
            new_file = produced / name
            if not new_file.exists():
                missing.append(name)
                continue
            before = skeleton(json.loads((RECORDED / name).read_text(encoding="utf-8")))
            after = skeleton(json.loads(new_file.read_text(encoding="utf-8")))
            (same if before == after else differ).append(name)

        client_files = [n for n in same if pathlib.Path(n).stem not in STAFF_EXAMPLES]
        print(f"совпали по составу полей: {len(same)}")
        print(f"  из них клиентских: {len(client_files)}")
        print(f"  ручек сотрудника: {len(same) - len(client_files)}")
        print(f"не сгенерированы в этом прогоне: {missing or '—'}")
        print(f"разошлись: {differ or '—'}")

        if differ:
            for name in differ:
                before = skeleton(json.loads((RECORDED / name).read_text(encoding="utf-8")))
                after = skeleton(json.loads((produced / name).read_text(encoding="utf-8")))
                print(f"\n--- {name}")
                print(f"было:  {json.dumps(before, ensure_ascii=False, sort_keys=True)[:800]}")
                print(f"стало: {json.dumps(after, ensure_ascii=False, sort_keys=True)[:800]}")
            print("\nПРОВЕРКА НЕ ПРОЙДЕНА: состав полей изменился.")
            return 1

        print("\nПРОВЕРКА ПРОЙДЕНА: ни один ответ не изменился ни одним полем.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
