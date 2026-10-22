from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.assistant.models import Conversation, KnowledgeDocument, Turn
from app.core.db import SessionLocal, engine
from app.models import User


def test_migration_preserves_banking_rows_and_matches_models():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    tables = ("users", "companies", "bureau_ratings", "existing_loans", "applications", "news")

    def snapshot():
        with engine.connect() as conn:
            return {table: [tuple(row) for row in conn.execute(text(f"SELECT * FROM {table} ORDER BY 1"))]
                    for table in tables}

    before = snapshot()
    for model in (Turn, KnowledgeDocument, Conversation):
        model.__table__.drop(engine)
    command.stamp(config, "20261022_02")
    command.upgrade(config, "head")
    assert snapshot() == before
    inspector = inspect(engine)
    for model in (Conversation, KnowledgeDocument, Turn):
        table = model.__table__
        assert {c["name"] for c in inspector.get_columns(table.name)} == set(table.columns.keys())
        assert {i["name"] for i in inspector.get_indexes(table.name)} == {i.name for i in table.indexes}
        assert len(inspector.get_foreign_keys(table.name)) == len(table.foreign_keys)
    with SessionLocal() as db:
        user = db.query(User).first()
        db.add(Conversation(id="migration-check", owner_id=user.id, audience="client", title="Preserve"))
        db.commit()
    command.upgrade(config, "head")
    with SessionLocal() as db:
        assert db.get(Conversation, "migration-check").title == "Preserve"
    command.downgrade(config, "20261022_02")
    assert not any(name.startswith("assistant_") for name in inspect(engine).get_table_names())
    assert snapshot() == before
    command.upgrade(config, "head")
