"""Уникальность активной заявки: один черновик на компанию и способ займа

Ревизия добавляет только частичный уникальный индекс на существующую таблицу
applications. Столбцы и данные не меняются: индекс покрывает лишь активные
статусы, поэтому завершённые и отклонённые заявки по той же компании остаются
как есть, и их может быть сколько угодно.

Перед созданием ревизия проверяет базу на уже существующие дубли. Если дубли
есть, она останавливается и печатает их, вместо того чтобы молча менять чужие
данные: какую из двух заявок закрыть — решение бизнеса, не миграции.

Revision ID: 20261022_02
Revises: 20261022_01
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models import ACTIVE_APPLICATION_INDEX, ACTIVE_APPLICATION_WHERE

revision: str = "20261022_02"
down_revision: Union[str, None] = "20261022_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_indexes() -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("applications")}


def _duplicate_groups() -> list[tuple]:
    rows = op.get_bind().execute(sa.text(
        "SELECT company_id, borrowing_mode, COUNT(*) AS n, MIN(id) AS first_id, MAX(id) AS last_id "
        f"FROM applications WHERE {ACTIVE_APPLICATION_WHERE} "
        "GROUP BY company_id, borrowing_mode HAVING COUNT(*) > 1"
    )).all()
    return [tuple(r) for r in rows]


def upgrade() -> None:
    if ACTIVE_APPLICATION_INDEX in _existing_indexes():
        return

    duplicates = _duplicate_groups()
    if duplicates:
        rows = "; ".join(f"компания {c}, способ {m}: {n} активных заявок (id {a}..{b})"
                         for c, m, n, a, b in duplicates)
        raise RuntimeError(
            "В базе уже есть компании с несколькими активными заявками одного способа займа, "
            f"уникальный индекс на такие данные не встанет: {rows}. "
            "Закройте лишние заявки (статус REJECTED или COMPLETED) и повторите миграцию."
        )

    op.create_index(ACTIVE_APPLICATION_INDEX, "applications", ["company_id", "borrowing_mode"],
                    unique=True,
                    postgresql_where=sa.text(ACTIVE_APPLICATION_WHERE),
                    sqlite_where=sa.text(ACTIVE_APPLICATION_WHERE))


def downgrade() -> None:
    """Откат убирает только индекс. Заявки не затрагиваются."""
    if ACTIVE_APPLICATION_INDEX in _existing_indexes():
        op.drop_index(ACTIVE_APPLICATION_INDEX, table_name="applications")
