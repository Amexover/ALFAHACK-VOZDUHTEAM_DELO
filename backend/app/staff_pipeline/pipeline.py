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

from app.core.errors import conflict
from app.enums import DecisionKind, Status
from app.models import Application, Decision, utcnow
from app.services import applications as svc
from app.staff_pipeline import auto_policy, scoring
from app.staff_pipeline.enums import (
    STAGE_LIMIT_HOURS,
    PipelineAction,
    PipelineEventType,
    PipelineStage,
    SnapshotReason,
)
from app.staff_pipeline.models import ApplicationPipeline, PipelineEvent
from app.staff_pipeline.security import DepartmentMember

SYSTEM_ACTOR = "Система"

# Статусы, при которых обработка в отделе закончена. Тот же перечень, по которому
# скоринг считает оценку зафиксированной: решение вынесено — разбор больше не меняется.
TERMINAL_STATUSES = scoring.DECIDED_STATUSES


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
    # Оценка фиксируется снимком уже на приёме: дальше правки правил её не меняют.
    snapshot = scoring.ensure_intake_snapshot(db, app)
    if (app.status == Status.IN_REVIEW and not app.decisions
            and auto_policy.matches(scoring.snapshot_evaluation(snapshot))):
        _auto_reject(db, app, pl, snapshot)
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
    # Все пути приёма берут ту же блокировку, что решения: политика не может
    # перезаписать решение сотрудника при одновременном открытии очереди.
    return list(db.scalars(select(Application).where(Application.status != Status.DRAFT)
                           .order_by(Application.id).with_for_update()))


def _auto_reject(db: Session, app: Application, pl: ApplicationPipeline, intake) -> None:
    now = utcnow()
    decision = Decision(application_id=app.id, kind=DecisionKind.REJECTED,
                        reject_reason_code=auto_policy.REJECT_REASON,
                        created_by=auto_policy.DECISION_AUTHOR, is_active=True)
    app.decisions.append(decision)
    app.status = Status.REJECTED
    app.decided_at = now
    pl.auto_rejected = True
    _enter_stage(pl, PipelineStage.DONE, now)
    snapshot = scoring.take_snapshot(db, app, SnapshotReason.ON_DECISION)
    add_event(db, app.id, PipelineEventType.AUTO_REJECTED,
              payload={"decision_id": decision.id, "policy_key": auto_policy.POLICY_KEY,
                       "policy_version": auto_policy.POLICY_VERSION,
                       "score_snapshot_id": snapshot.id, "intake_snapshot_id": intake.id,
                       "ruleset_version": snapshot.ruleset_version,
                       "reason_code": auto_policy.REJECT_REASON})


def cancel_auto_reject(db: Session, member: DepartmentMember, app: Application,
                       pl: ApplicationPipeline, reason: str) -> Decision:
    decision = svc.active_decision(app)
    event = next((e for e in reversed(history(db, app.id))
                  if e.type == PipelineEventType.AUTO_REJECTED), None)
    if (decision is None or decision.kind != DecisionKind.REJECTED or event is None
            or event.payload.get("decision_id") != decision.id):
        raise conflict("NOT_AUTO_REJECTED", "Автоматическое решение уже не действует")
    other = svc.active_application(db, app.company_id, app.borrowing_mode)
    if other is not None and other.id != app.id:
        raise conflict("ACTIVE_APPLICATION_EXISTS", "У компании уже есть активная заявка этого способа займа")
    decision.is_active = False
    app.status = Status.IN_REVIEW
    app.decided_at = None
    pl.auto_rejected = False
    _enter_stage(pl, PipelineStage.UNDERWRITING, utcnow())
    pl.assignee_id = member.user.id
    pl.assigned_at = utcnow()
    add_event(db, app.id, PipelineEventType.AUTO_REJECT_CANCELLED, member, comment=reason,
              payload={"decision_id": decision.id, "auto_reject_event_id": event.id,
                       "score_snapshot_id": event.payload["score_snapshot_id"]})
    return decision


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
    """Решение закрывает обработку. Исполнитель остаётся в записи — видно, кто решил.

    Здесь же снимается второй снимок оценки: по какому разбору вынесено решение.
    Снимок живёт в одной транзакции с самим решением — если решение не пройдёт,
    снимка не останется.
    """
    _enter_stage(pl, PipelineStage.DONE, utcnow())
    snapshot = scoring.take_snapshot(db, app, SnapshotReason.ON_DECISION)
    add_event(db, app.id, PipelineEventType.DECISION_MADE, member, comment=comment,
              payload={"action": action.value, "score_snapshot_id": snapshot.id,
                       "total_score": snapshot.total_score,
                       "recommendation": snapshot.recommendation,
                       "ruleset_version": snapshot.ruleset_version, **(payload or {})})
