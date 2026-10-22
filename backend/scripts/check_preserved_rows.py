"""Снимок прежних строк базы; сравнение доказывает отсутствие потерь при миграции.

python -m scripts.check_preserved_rows > before.json
python -m scripts.check_preserved_rows --compare before.json
Проверка допускает добавление новых строк сидом отдела, но требует прежние без изменений.
"""
import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from app.core.db import engine

TABLES = ("users", "companies", "bureau_ratings", "existing_loans", "applications",
          "application_events", "info_requests", "decisions", "news")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    snapshot = {}
    with engine.connect() as db:
        for table in TABLES:
            rows = db.execute(text(f"select * from {table}")).mappings().all()
            key = "company_id" if table == "bureau_ratings" else "id"
            snapshot[table] = {
                str(row[key]): hashlib.sha256(json.dumps(dict(row), sort_keys=True, default=str,
                                                       ensure_ascii=False).encode()).hexdigest() for row in rows}
    if args.compare:
        before = json.loads(args.compare.read_text(encoding="utf-8"))
        mismatches = [(t, k) for t, rows in before.items() for k, value in rows.items()
                      if snapshot[t].get(k) != value]
        if mismatches:
            raise SystemExit(f"Старые строки потеряны или изменились: {mismatches}")
        print(json.dumps({"result": "PASS", "preserved_rows": sum(map(len, before.values())),
                          "tables": len(before)}, ensure_ascii=False))
    else:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
