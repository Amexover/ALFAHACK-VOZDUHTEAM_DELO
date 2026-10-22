"""Таблицы отдела сотрудников.

Ни одна строка здесь не меняет существующие таблицы: все поля отдела лежат в
собственных таблицах и подключаются к users и applications по внешнему ключу.
Поэтому миграция ничего не переписывает в заполненной базе — только добавляет.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.db import Base
from app.models import User, utcnow
from app.staff_pipeline.enums import PipelineStage


class StaffProfile(Base):
    """Роль сотрудника внутри отдела.

    Отдельная таблица, а не колонка в users: общий перечень ролей трогать нельзя —
    маскировка ФИО сотрудника в истории заявки завязана на текущее значение users.role.
    """

    __tablename__ = "staff_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    staff_role: Mapped[str] = mapped_column(String(20))
    # Учётные записи сотрудников, существовавшие до появления отдела, работают в прежнем
    # режиме: правила конвейера к ним не применяются, их поведение менять нельзя.
    pipeline_enforced: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApplicationPipeline(Base):
    """Состояние заявки во внутреннем конвейере: этап, исполнитель, время этапа."""

    __tablename__ = "application_pipeline"

    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), primary_key=True)
    stage: Mapped[str] = mapped_column(String(30), default=PipelineStage.VERIFICATION, index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stage_entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Начало текущего ожидания ответа клиента; None — заявка не ждёт клиента.
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Сколько секунд этапа уже было потрачено на ожидание клиента — в норматив не идёт.
    waiting_seconds_total: Mapped[int] = mapped_column(Integer, default=0)
    # Этап, с которого запросили сведения: ответ клиента возвращает заявку сюда, а не в начало.
    stage_before_waiting: Mapped[str | None] = mapped_column(String(30))
    auto_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assignee: Mapped[User | None] = relationship()


class PipelineEvent(Base):
    """Внутренняя история обработки. Только добавление, задним числом не правится.

    Клиенту не отдаётся никогда — это отдельная таблица, а не общая история заявки.
    """

    __tablename__ = "pipeline_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(200))
    actor_staff_role: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScoreSnapshot(Base):
    """Снимок оценки: зафиксированный разбор по правилам на момент приёма и решения."""

    __tablename__ = "score_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    ruleset_version: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(20))
    total_score: Mapped[int] = mapped_column(Integer)
    recommendation: Mapped[str] = mapped_column(String(20))
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PipelineHistoryIsAppendOnly(RuntimeError):
    """Внутреннюю историю обработки нельзя править и удалять задним числом."""


class ScoreSnapshotIsImmutable(RuntimeError):
    """Снимок оценки нельзя переписать: иначе обоснование решения меняется задним числом."""


@event.listens_for(Session, "before_flush")
def _history_is_append_only(session: Session, flush_context, instances) -> None:
    """Историю обработки и снимки оценки можно только добавлять.

    Не соглашение на словах, а запрет на уровне сессии: любая попытка изменить
    или удалить такую запись обрывает транзакцию целиком.
    """
    for obj in session.dirty:
        if isinstance(obj, PipelineEvent) and session.is_modified(obj, include_collections=False):
            raise PipelineHistoryIsAppendOnly(
                f"Запись истории обработки #{obj.id} изменять нельзя — история только пополняется"
            )
        if isinstance(obj, ScoreSnapshot) and session.is_modified(obj, include_collections=False):
            raise ScoreSnapshotIsImmutable(
                f"Снимок оценки #{obj.id} изменять нельзя — оценка фиксируется один раз"
            )
    for obj in session.deleted:
        if isinstance(obj, PipelineEvent):
            raise PipelineHistoryIsAppendOnly(
                f"Запись истории обработки #{obj.id} удалять нельзя — история только пополняется"
            )
        if isinstance(obj, ScoreSnapshot):
            raise ScoreSnapshotIsImmutable(
                f"Снимок оценки #{obj.id} удалять нельзя — оценка фиксируется один раз"
            )
