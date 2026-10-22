"""Отдел сотрудников: роли внутри отдела, конвейер, внутренняя история, снимки оценки

Ревизия добавляет только новые таблицы и не трогает существующие: заявки, компании,
пользователи и история заявки остаются как есть, данные не переносятся и не теряются.

Каждое создание проверяется по факту: ревизия не падает, если таблица уже есть
(на пустой базе таблицы создаёт Base.metadata.create_all при старте приложения).

Revision ID: 20261022_01
Revises:
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261022_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def _create_index(name: str, table: str, columns: list[str]) -> None:
    if name not in _existing_indexes(table):
        op.create_index(name, table, columns)


def upgrade() -> None:
    tables = _existing_tables()

    if "staff_profiles" not in tables:
        op.create_table(
            "staff_profiles",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("staff_role", sa.String(length=20), nullable=False),
            sa.Column("pipeline_enforced", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_staff_profiles_user"),
            sa.PrimaryKeyConstraint("user_id", name="pk_staff_profiles"),
        )

    if "application_pipeline" not in tables:
        op.create_table(
            "application_pipeline",
            sa.Column("application_id", sa.Integer(), nullable=False),
            sa.Column("stage", sa.String(length=30), nullable=False),
            sa.Column("assignee_id", sa.Integer(), nullable=True),
            sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("stage_entered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("waiting_since", sa.DateTime(timezone=True), nullable=True),
            sa.Column("waiting_seconds_total", sa.Integer(), nullable=False),
            sa.Column("stage_before_waiting", sa.String(length=30), nullable=True),
            sa.Column("auto_rejected", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["application_id"], ["applications.id"], name="fk_pipeline_application"),
            sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], name="fk_pipeline_assignee"),
            sa.PrimaryKeyConstraint("application_id", name="pk_application_pipeline"),
        )
    _create_index("ix_application_pipeline_stage", "application_pipeline", ["stage"])
    _create_index("ix_application_pipeline_assignee_id", "application_pipeline", ["assignee_id"])

    if "pipeline_events" not in tables:
        op.create_table(
            "pipeline_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("application_id", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=40), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("actor_name", sa.String(length=200), nullable=False),
            sa.Column("actor_staff_role", sa.String(length=20), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["application_id"], ["applications.id"], name="fk_pipeline_events_application"),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_pipeline_events_actor"),
            sa.PrimaryKeyConstraint("id", name="pk_pipeline_events"),
        )
    _create_index("ix_pipeline_events_application_id", "pipeline_events", ["application_id"])

    if "score_snapshots" not in tables:
        op.create_table(
            "score_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("application_id", sa.Integer(), nullable=False),
            sa.Column("ruleset_version", sa.String(length=20), nullable=False),
            sa.Column("reason", sa.String(length=20), nullable=False),
            sa.Column("total_score", sa.Integer(), nullable=False),
            sa.Column("recommendation", sa.String(length=20), nullable=False),
            sa.Column("breakdown", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["application_id"], ["applications.id"], name="fk_score_snapshots_application"),
            sa.PrimaryKeyConstraint("id", name="pk_score_snapshots"),
        )
    _create_index("ix_score_snapshots_application_id", "score_snapshots", ["application_id"])


def downgrade() -> None:
    """Откат убирает только наши таблицы. Чужие данные не затрагиваются."""
    tables = _existing_tables()
    for name in ("score_snapshots", "pipeline_events", "application_pipeline", "staff_profiles"):
        if name in tables:
            op.drop_table(name)
