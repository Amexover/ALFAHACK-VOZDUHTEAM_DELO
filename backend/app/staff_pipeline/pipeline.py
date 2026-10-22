"""Внутренний конвейер обработки заявки: этап, исполнитель, сроки, история.

Два слоя состояний. Снаружи у заявки прежний статус — его видит клиент, и он не
меняется. Внутри — этап конвейера, он живёт в своей таблице и клиенту не отдаётся.

Этап не обновляется фоновой задачей: состояние приводится в соответствие со статусом
заявки в момент запроса. Поэтому проект по-прежнему поднимается одной командой —
ни планировщика, ни отдельных процессов в проекте не появилось.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import Status
from app.models import Application, utcnow
from app.staff_pipeline.enums import (
    STAGE_LIMIT_HOURS,
    PipelineAction,
    PipelineEventType,
    PipelineStage,
)
from app.staff_pipeline.models import ApplicationPipeline, PipelineEvent
from app.staff_pipeline.security import DepartmentMember

SYSTEM_ACTOR = "Система"

# Статусы, при которых обработка в отделе закончена.
TERMINAL_STATUSES = (Status.APPROVED, Status.COUNTER_OFFER, Status.REJECTED, Status.COMPLETED)


def as_utc(moment: datetime) -> datetime:
    """SQLite отдаёт время без зоны — приводим к UTC, чтобы арифметика не падала."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def stage_of(pl: ApplicationPipeline) -> PipelineStage:
    return PipelineStage(pl.stage)


# ---------- внутренняя история ----------

def add_event(db: Session, application_id: int, type_: PipelineEventType,
              member: DepartmentMember | None = None, comment: str | None = None,
              payload: dict | None = None) -> PipelineEvent:
    """Добавляет запись во внутреннюю историю. Правок задним числом нет — только добавление."""
    event = PipelineEvent(
        application_id=application_id,
        type=type_,
        actor_id=member.user.id if member else None,
        actor_name=member.user.full_name if member else SYSTEM_ACTOR,
        actor_staff_role=member.staff_role.value if member and member.staff_role else None,
        comment=comment,
        payload=payload or {},
    )
    db.add(event)
    return event


def history(db: Session, application_id: int) -> list[PipelineEvent]:
    return list(db.scalars(
        select(PipelineEvent).where(PipelineEvent.application_id == application_id)
        .order_by(PipelineEvent.id)
    ))


# ---------- приём в конвейер и сверка со статусом ----------

def _enter_stage(pl: ApplicationPipeline, stage: PipelineStage, now: datetime) -> None:
    pl.stage = stage
    pl.stage_entered_at = now
    pl.waiting_seconds_total = 0
    pl.waiting_since = None
    pl.stage_before_waiting = None


def _open_request_at(app: Application) -> datetime | None:
    request = next((r for r in reversed(app.info_requests) if r.answered_at is None), None)
    return as_utc(request.created_at) if request else None


def _intake(db: Session, app: Application) -> ApplicationPipeline:
    """Заявка принимается в конвейер при первом появлении у сотрудника.

    Отдельной ручки «принять в конвейер» нет: клиентская ручка отправки не меняется.
    Отсчёт норматива идёт от времени подачи, а не от момента, когда заявку открыли.
    """
    pl = ApplicationPipeline(
        application_id=app.id,
        stage=PipelineStage.VERIFICATION,
        stage_entered_at=as_utc(app.submitted_at or app.created_at or utcnow()),
        waiting_seconds_total=0,
        auto_rejected=False,
    )
    db.add(pl)
    add_event(db, app.id, PipelineEventType.ACCEPTED_TO_PIPELINE,
              payload={"stage": PipelineStage.VERIFICATION.value, "status": app.status})
    db.flush()
    return pl


def _sync(db: Session, app: Application, pl: ApplicationPipeline) -> None:
    """Приводит этап в соответствие со статусом заявки.

    Клиентские ручки мы не трогаем, поэтому о действиях клиента узнаём по статусу:
    запрос сведений останавливает отсчёт норматива, а ответ клиента возвращает заявку
    на тот этап, с которого сведения запрашивали, а не в начало.
    """
    status = Status(app.status)
    now = utcnow()

    if status == Status.NEED_INFO and pl.waiting_since is None:
        pl.waiting_since = _open_request_at(app) or now
        pl.stage_before_waiting = pl.stage
    elif status != Status.NEED_INFO and pl.waiting_since is not None:
        waiting_since = as_utc(pl.waiting_since)
        # Сотрудник может открыть заявку намного позже ответа клиента. Исключаем
        # только само ожидание, включая случай передачи на другой этап во время паузы.
        answered_at = next((as_utc(r.answered_at) for r in reversed(app.info_requests)
                            if r.answered_at is not None and as_utc(r.answered_at) >= waiting_since), now)
        pl.waiting_seconds_total += max(0, int((answered_at - waiting_since).total_seconds()))
        if pl.stage_before_waiting:
            pl.stage = pl.stage_before_waiting
        pl.waiting_since = None
        pl.stage_before_waiting = None
        response_event = add_event(db, app.id, PipelineEventType.INFO_PROVIDED, payload={"stage": pl.stage})
        response_event.created_at = answered_at

    if status in TERMINAL_STATUSES and pl.stage != PipelineStage.DONE:
        _enter_stage(pl, PipelineStage.DONE, as_utc(app.decided_at) if app.decided_at else now)
    elif status == Status.IN_REVIEW and pl.stage == PipelineStage.DONE:
        # Клиент дополнил заявку после решения: решение снято, сведения надо проверить заново.
        _enter_stage(pl, PipelineStage.VERIFICATION, now)
        pl.assignee_id = None
        pl.assigned_at = None
        add_event(db, app.id, PipelineEventType.RETURNED_TO_VERIFICATION,
                  payload={"reason": "client_supplemented"})


def ensure(db: Session, app: Application) -> ApplicationPipeline:
    """Состояние конвейера по заявке; при первой встрече заявка принимается в конвейер.

    Вызывается и на чтение, и на действие. Изменения только записываются в сессию —
    фиксирует их вызывающая сторона.
    """
    pl = db.get(ApplicationPipeline, app.id)
    if pl is None:
        try:
            with db.begin_nested():
                pl = _intake(db, app)
        except IntegrityError:
            # Два сотрудника открыли очередь одновременно: приём в конвейер уже сделал первый.
            pl = db.get(ApplicationPipeline, app.id)
    _sync(db, app, pl)
    db.flush()
    return pl


def ensure_all(db: Session, apps: list[Application]) -> list[tuple[Application, ApplicationPipeline]]:
    return [(app, ensure(db, app)) for app in apps]


def submitted_applications(db: Session) -> list[Application]:
    return list(db.scalars(select(Application).where(Application.status != Status.DRAFT)))


# ---------- сроки ----------

def timing(pl: ApplicationPipeline) -> dict:
    """Срок по текущему этапу. Считается в момент запроса.

    Время ожидания ответа клиента в норматив не идёт: пока заявка ждёт клиента,
    отсчёт остановлен и просрочка не наступает — банк не отвечает за молчание клиента.
    """
    stage = stage_of(pl)
    waiting = pl.waiting_since is not None
    limit_hours = STAGE_LIMIT_HOURS.get(stage)
    if limit_hours is None:
        return {
            "stage_limit_hours": None,
            "stage_entered_at": as_utc(pl.stage_entered_at),
            "deadline_at": None,
            "time_left_minutes": None,
            "is_overdue": False,
            "waiting_for_client": waiting,
            "waiting_minutes_total": pl.waiting_seconds_total // 60,
        }
    now = utcnow()
    reference = as_utc(pl.waiting_since) if waiting else now
    spent = (reference - as_utc(pl.stage_entered_at)).total_seconds() - pl.waiting_seconds_total
    left = limit_hours * 3600 - spent
    return {
        "stage_limit_hours": limit_hours,
        "stage_entered_at": as_utc(pl.stage_entered_at),
        "deadline_at": now + timedelta(seconds=left),
        "time_left_minutes": int(left // 60),
        "is_overdue": left < 0 and not waiting,
        "waiting_for_client": waiting,
        "waiting_minutes_total": pl.waiting_seconds_total // 60,
    }


def is_overdue(pl: ApplicationPipeline) -> bool:
    return bool(timing(pl)["is_overdue"])


# ---------- переходы ----------

def claim(db: Session, member: DepartmentMember, app: Application, pl: ApplicationPipeline) -> None:
    pl.assignee_id = member.user.id
    pl.assigned_at = utcnow()
    add_event(db, app.id, PipelineEventType.CLAIMED, member, payload={"stage": pl.stage})


def release(db: Session, member: DepartmentMember, app: Application, pl: ApplicationPipeline,
            comment: str | None = None) -> None:
    pl.assignee_id = None
    pl.assigned_at = None
    add_event(db, app.id, PipelineEventType.RELEASED, member, comment=comment, payload={"stage": pl.stage})


def pass_to_underwriting(db: Session, member: DepartmentMember, app: Application,
                         pl: ApplicationPipeline, comment: str | None = None) -> None:
    """Передача на этап решения. Исполнитель снимается: андеррайтер берёт заявку сам."""
    now = utcnow()
    waiting = pl.waiting_since is not None
    _enter_stage(pl, PipelineStage.UNDERWRITING, now)
    if waiting:
        # Заявка ушла дальше, не дождавшись клиента: ответ клиента вернёт её сюда же.
        pl.waiting_since = now
        pl.stage_before_waiting = PipelineStage.UNDERWRITING
    pl.assignee_id = None
    pl.assigned_at = None
    add_event(db, app.id, PipelineEventType.PASSED_TO_UNDERWRITING, member, comment=comment)


def record_info_request(db: Session, member: DepartmentMember, app: Application,
                        pl: ApplicationPipeline, message: str, fields: list[str]) -> None:
    """Запрос сведений: отсчёт норматива останавливается до ответа клиента."""
    if pl.waiting_since is None:
        pl.waiting_since = utcnow()
        pl.stage_before_waiting = pl.stage
    add_event(db, app.id, PipelineEventType.INFO_REQUESTED, member, comment=message,
              payload={"fields": list(fields), "stage": pl.stage})


def record_decision(db: Session, member: DepartmentMember, app: Application, pl: ApplicationPipeline,
                    action: PipelineAction, comment: str | None = None,
                    payload: dict | None = None) -> None:
    """Решение закрывает обработку. Исполнитель остаётся в записи — видно, кто решил."""
    _enter_stage(pl, PipelineStage.DONE, utcnow())
    add_event(db, app.id, PipelineEventType.DECISION_MADE, member, comment=comment,
              payload={"action": action.value, **(payload or {})})
