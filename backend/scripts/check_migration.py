"""Проверка миграции на заполненной базе.

Сценарий воспроизводит состояние сервера: база, созданная прежней версией
приложения (без таблиц отдела), с демонстрационными данными и отправленными
заявками. На неё накатывается миграция, затем сверяются данные.

Запуск:  python scripts/check_migration.py
Вывод пригоден для протокола приёмки (docs/staff-pipeline/MIGRATION_CHECK.txt).
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable
OLD_TABLES = ["users", "companies", "bureau_ratings", "existing_loans", "applications",
              "application_events", "info_requests", "decisions", "news"]
NEW_TABLES = ["staff_profiles", "application_pipeline", "pipeline_events", "score_snapshots"]

FILL_OLD_BASE = r'''
import json
from datetime import timedelta
from app.seed import init_db           # импортирует только прежние модели
from app.core.db import SessionLocal
from app.enums import BorrowingMode, EventType, ProductId, Role, Status
from app.models import Application, ApplicationEvent, Company, User, utcnow

init_db()                              # прежняя схема: таблиц отдела в метаданных нет
with SessionLocal() as db:
    owner = db.query(User).filter(User.login == "alexey").one()
    company = db.query(Company).filter(Company.owner_id == owner.id).first()
    now = utcnow()
    app = Application(company_id=company.id, borrowing_mode=BorrowingMode.NEW_CREDIT,
                      product_id=ProductId.WORKING_CAPITAL, amount=900_000, term_months=12,
                      business_profile={"industry": "Торговля", "months_operating": 40},
                      status=Status.IN_REVIEW, submitted_at=now - timedelta(hours=5))
    db.add(app)
    db.flush()
    app.number = f"D-{now.year}-{app.id:06d}"
    db.add(ApplicationEvent(application_id=app.id, type=EventType.SUBMITTED, actor_role=Role.CLIENT,
                            actor_name=owner.full_name, payload={}))
    db.commit()
print(json.dumps({"ok": True}))
'''

FILL_NEW_BASE = r'''
import json
from app.main import app              # полная сборка: create_all создаёт и таблицы отдела
from fastapi.testclient import TestClient
with TestClient(app):
    pass
print(json.dumps({"ok": True}))
'''


def run(code: str, db_url: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url, "DEPARTMENT_DEMO_QUEUE": "true", "PYTHONIOENCODING": "utf-8"}
    env.pop("PYTEST_CURRENT_TEST", None)
    r = subprocess.run([PY, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"не удалось подготовить базу:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def alembic(command: list[str], db_url: str, expect_ok: bool = True) -> str:
    env = {**os.environ, "DATABASE_URL": db_url, "PYTHONIOENCODING": "utf-8"}
    env.pop("PYTEST_CURRENT_TEST", None)
    r = subprocess.run([PY, "-m", "alembic", "-c", "alembic.ini", *command], cwd=BACKEND, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    out = (r.stdout or "") + (r.stderr or "")
    if expect_ok and r.returncode != 0:
        raise SystemExit(f"alembic {' '.join(command)} упал:\n{out}")
    return out.strip()


SNAPSHOT = r'''
import json, sys
from sqlalchemy import create_engine, inspect, text
url = sys.argv[1]
engine = create_engine(url)
with engine.connect() as c:
    tables = sorted(inspect(engine).get_table_names())
    counts = {t: c.execute(text(f"select count(*) from {t}")).scalar() for t in tables}
print(json.dumps({"tables": tables, "counts": counts}, ensure_ascii=False))
'''


def snapshot(db_url: str) -> dict:
    r = subprocess.run([PY, "-c", SNAPSHOT, db_url], cwd=BACKEND, capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode != 0:
        raise SystemExit(r.stdout + r.stderr)
    return json.loads(r.stdout.strip().splitlines()[-1])


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'OK' if ok else 'ПРОВАЛ'}] {label}{(' — ' + detail) if detail else ''}")
    return ok


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="migration-check-"))
    ok = True

    print("Сценарий 1. Заполненная база прежней версии (как на сервере)")
    old_db = tmp / "filled.db"
    url = "sqlite:///" + old_db.as_posix()
    run(FILL_OLD_BASE, url)
    before = snapshot(url)
    print(f"  до миграции:    таблиц {len(before['tables'])}, данные {json.dumps({k: v for k, v in before['counts'].items() if v}, ensure_ascii=False)}")
    ok &= check("таблиц отдела в базе ещё нет", not any(t in before["tables"] for t in NEW_TABLES))

    print(f"  alembic upgrade head: {alembic(['upgrade', 'head'], url)!r}")
    after = snapshot(url)
    ok &= check("все четыре таблицы отдела появились",
                all(t in after["tables"] for t in NEW_TABLES), ", ".join(NEW_TABLES))
    ok &= check("данные прежних таблиц не изменились",
                all(before["counts"][t] == after["counts"][t] for t in OLD_TABLES),
                json.dumps({t: after["counts"][t] for t in OLD_TABLES}, ensure_ascii=False))
    ok &= check("версия схемы зафиксирована", after["counts"].get("alembic_version") == 1)

    print(f"  повторный alembic upgrade head: {alembic(['upgrade', 'head'], url)!r}")
    again = snapshot(url)
    ok &= check("повторный запуск не упал и ничего не продублировал",
                again["counts"] == after["counts"] and again["tables"] == after["tables"])

    print(f"  alembic downgrade base: {alembic(['downgrade', 'base'], url)!r}")
    rolled = snapshot(url)
    ok &= check("откат убрал только таблицы отдела",
                not any(t in rolled["tables"] for t in NEW_TABLES))
    ok &= check("после отката прежние данные на месте",
                all(before["counts"][t] == rolled["counts"][t] for t in OLD_TABLES))
    alembic(["upgrade", "head"], url)

    print()
    print("Сценарий 2. Пустая база, поднятая приложением (таблицы уже созданы create_all)")
    new_db = tmp / "fresh.db"
    url2 = "sqlite:///" + new_db.as_posix()
    run(FILL_NEW_BASE, url2)
    fresh = snapshot(url2)
    ok &= check("приложение создало таблицы отдела само",
                all(t in fresh["tables"] for t in NEW_TABLES))
    ok &= check("демо-данные отдела на месте",
                fresh["counts"]["applications"] >= 6 and fresh["counts"]["staff_profiles"] >= 3,
                f"заявок {fresh['counts']['applications']}, профилей сотрудников {fresh['counts']['staff_profiles']}")
    print(f"  alembic upgrade head: {alembic(['upgrade', 'head'], url2)!r}")
    fresh_after = snapshot(url2)
    ok &= check("миграция на уже созданных таблицах не падает и данные не трогает",
                {k: v for k, v in fresh_after["counts"].items() if k != "alembic_version"}
                == {k: v for k, v in fresh["counts"].items() if k != "alembic_version"})

    print()
    print("ИТОГ:", "все проверки пройдены" if ok else "есть провалы")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
