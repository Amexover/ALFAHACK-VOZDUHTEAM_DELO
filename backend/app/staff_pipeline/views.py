"""Представления отдела. Всё, что здесь собирается, уходит только в ручки сотрудника."""

from sqlalchemy.orm import Session

from app.models import Application
from app.services import applications as svc
from app.staff_pipeline import pipeline, rules
from app.staff_pipeline.enums import (
    PIPELINE_EVENT_LABELS,
    PIPELINE_STAGE_LABELS,
    STAFF_ROLE_LABELS,
    STAGE_LIMIT_HOURS,
    STAGE_OWNER_ROLE,
    PipelineEventType,
    PipelineStage,
    StaffRole,
)
from app.staff_pipeline.models import ApplicationPipeline, PipelineEvent
from app.staff_pipeline.security import DepartmentMember, staff_role_of

NO_ROLE_LABEL = "Сотрудник банка"

# Что роль может делать в конвейере. Фронтенд рисует по этому списку, а сервер
# проверяет те же права зависимостями — список не является единственной защитой.
PERMISSIONS = {
    StaffRole.VERIFIER: [
        "queue:view",
        "application:claim",
        "application:release",
        "info:request",
        "application:pass_to_underwriting",
    ],
    StaffRole.UNDERWRITER: [
        "queue:view",
        "application:claim",
        "application:release",
        "info:request",
        "application:decide",
        "application:cancel_auto_reject",
    ],
}

STAGE_NORMS = [
    {
        "stage": stage.value,
        "stage_label": PIPELINE_STAGE_LABELS[stage],
        "limit_hours": hours,
        "owner_staff_role": STAGE_OWNER_ROLE[stage].value,
    }
    for stage, hours in STAGE_LIMIT_HOURS.items()
]

PIPELINE_STAGES = [
    {"stage": s.value, "stage_label": PIPELINE_STAGE_LABELS[s]} for s in PipelineStage
]


def member_view(member: DepartmentMember) -> dict:
    role = member.staff_role
    return {
        "staff_role": role.value if role else None,
        "staff_role_label": STAFF_ROLE_LABELS[role] if role else NO_ROLE_LABEL,
        "is_verifier": member.is_verifier,
        "is_underwriter": member.is_underwriter,
        # Учётные записи, существовавшие до появления отдела, работают в прежнем режиме.
        "pipeline_enforced": member.pipeline_enforced,
        "permissions": PERMISSIONS.get(role, ["queue:view"]),
        "stage_norms": STAGE_NORMS,
        "stages": PIPELINE_STAGES,
    }


# ---------- конвейер ----------

def assignee_view(db: Session, pl: ApplicationPipeline) -> dict | None:
    user = pl.assignee
    if user is None:
        return None
    role = staff_role_of(db, user)
    return {"id": user.id, "full_name": user.full_name, "staff_role": role.value if role else None}


def pipeline_block(db: Session, member: DepartmentMember, app: Application,
                   pl: ApplicationPipeline) -> dict:
    """Блок конвейера для элемента очереди: этап, исполнитель, срок."""
    stage = pipeline.stage_of(pl)
    return {
        "stage": stage.value,
        "stage_label": PIPELINE_STAGE_LABELS[stage],
        "assignee": assignee_view(db, pl),
        "is_mine": pl.assignee_id == member.user.id,
        "claimable": rules.claimable(member, app, pl),
        **pipeline.timing(pl),
        "auto_rejected": bool(pl.auto_rejected),
    }


def queue_item_view(db: Session, member: DepartmentMember, app: Application,
                    pl: ApplicationPipeline) -> dict:
    """Элемент очереди отдела: то же краткое представление заявки плюс блок конвейера."""
    return {
        **svc.brief_view(app),
        "client_name": app.company.owner.full_name,
        "preliminary_rate": float(app.preliminary_rate) if app.preliminary_rate is not None else None,
        "pipeline": pipeline_block(db, member, app, pl),
    }


def history_event_view(event: PipelineEvent) -> dict:
    """Запись внутренней истории. Подпись приходит с сервера — собирать по ключу не нужно."""
    try:
        label = PIPELINE_EVENT_LABELS[PipelineEventType(event.type)]
    except ValueError:  # неизвестный тип не должен ронять карточку
        label = event.type
    return {
        "id": event.id,
        "type": event.type,
        "label": label,
        "actor_name": event.actor_name,
        "actor_staff_role": event.actor_staff_role,
        "comment": event.comment,
        "payload": event.payload or {},
        "created_at": event.created_at,
    }


def pipeline_view(db: Session, member: DepartmentMember, app: Application,
                  pl: ApplicationPipeline) -> dict:
    """Внутренняя карточка конвейера: этап, срок, доступные действия и история обработки.

    Отдельная ручка, а не поле в существующей карточке заявки: тело чужих функций
    мы не меняем. Клиенту этот блок не отдаётся ни в каком виде.
    """
    return {
        "application_id": app.id,
        "number": app.number,
        "status": app.status,
        **pipeline_block(db, member, app, pl),
        "available_actions": rules.allowed(member, app, pl),
        "history": [history_event_view(e) for e in pipeline.history(db, app.id)],
    }
