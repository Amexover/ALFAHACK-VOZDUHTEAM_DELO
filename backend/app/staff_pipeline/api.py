"""Ручки отдела сотрудников. Префикс /staff, пути не пересекаются с существующими ручками."""

from enum import StrEnum

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import user_view
from app.core.db import get_db
from app.models import Application
from app.services import applications as svc
from app.staff_pipeline import pipeline, rules
from app.staff_pipeline.enums import PipelineAction, PipelineStage
from app.staff_pipeline.models import ApplicationPipeline
from app.staff_pipeline.schemas import CommentIn
from app.staff_pipeline.security import DepartmentMember, current_member
from app.staff_pipeline.views import member_view, pipeline_view, queue_item_view

router = APIRouter(prefix="/staff", tags=["staff-department"])


class QueueScope(StrEnum):
    """Срезы очереди: свободные, мои в работе, просроченные, все."""

    FREE = "free"
    MINE = "mine"
    OVERDUE = "overdue"
    ALL = "all"


@router.get("/me")
def me(member: DepartmentMember = Depends(current_member)):
    """«Кто я» внутри отдела: общая учётная запись плюс роль, права и нормативы этапов."""
    return {"user": user_view(member.user), "department": member_view(member)}


def _in_scope(scope: QueueScope, member: DepartmentMember, pl: ApplicationPipeline, block: dict) -> bool:
    if scope == QueueScope.ALL:
        return True
    open_stage = pipeline.stage_of(pl) != PipelineStage.DONE
    if scope == QueueScope.FREE:
        return open_stage and pl.assignee_id is None
    if scope == QueueScope.MINE:
        return open_stage and pl.assignee_id == member.user.id
    return bool(block["is_overdue"])


@router.get("/queue")
def queue(scope: QueueScope = QueueScope.FREE, stage: PipelineStage | None = None,
          q: str | None = Query(None, max_length=200),
          member: DepartmentMember = Depends(current_member), db: Session = Depends(get_db)):
    """Очередь отдела со сроками по этапу.

    Сроки считаются в момент запроса: ни планировщика, ни фоновых задач в проекте нет.
    Заявки, попавшие в очередь впервые, здесь же принимаются в конвейер.
    """
    rows = pipeline.ensure_all(db, pipeline.submitted_applications(db))
    db.commit()

    items = [queue_item_view(db, member, app, pl) for app, pl in rows]
    counts = {
        s.value: sum(1 for (_, pl), item in zip(rows, items) if _in_scope(s, member, pl, item["pipeline"]))
        for s in QueueScope
    }

    needle = (q or "").strip().lower()
    selected = [
        item for (_, pl), item in zip(rows, items)
        if _in_scope(scope, member, pl, item["pipeline"])
        and (stage is None or item["pipeline"]["stage"] == stage.value)
        and (not needle or needle in (item["number"] or "").lower() or needle in item["company_name"].lower())
    ]
    # Срочное — выше: сначала просроченные, затем те, у кого меньше времени до срока.
    selected.sort(key=lambda i: (i["pipeline"]["time_left_minutes"] is None,
                                 i["pipeline"]["time_left_minutes"] or 0))
    return {"scope": scope.value, "counts": counts, "items": selected}


def _load(db: Session, application_id: int, lock: bool = False) -> tuple[Application, ApplicationPipeline]:
    app = svc.get_for_staff(db, application_id, lock=lock)
    return app, pipeline.ensure(db, app)


@router.get("/applications/{application_id}/pipeline")
def application_pipeline(application_id: int, member: DepartmentMember = Depends(current_member),
                         db: Session = Depends(get_db)):
    """Внутренняя карточка конвейера и история обработки. Клиенту не отдаётся никогда."""
    app, pl = _load(db, application_id)
    db.commit()
    return pipeline_view(db, member, app, pl)


@router.post("/applications/{application_id}/claim")
def claim(application_id: int, member: DepartmentMember = Depends(current_member),
          db: Session = Depends(get_db)):
    """Взять свободную заявку в работу. Занятую не отдаём — в ответе видно, кто её держит."""
    app, pl = _load(db, application_id, lock=True)
    rules.require(member, app, pl, PipelineAction.CLAIM)
    pipeline.claim(db, member, app, pl)
    db.commit()
    return pipeline_view(db, member, app, pl)


@router.post("/applications/{application_id}/release")
def release(application_id: int, body: CommentIn | None = None,
            member: DepartmentMember = Depends(current_member), db: Session = Depends(get_db)):
    """Вернуть свою заявку в очередь. Попадает во внутреннюю историю обработки."""
    app, pl = _load(db, application_id, lock=True)
    rules.require(member, app, pl, PipelineAction.RELEASE)
    pipeline.release(db, member, app, pl, comment=(body.comment or "").strip() or None if body else None)
    db.commit()
    return pipeline_view(db, member, app, pl)


@router.post("/applications/{application_id}/pass-to-underwriting")
def pass_to_underwriting(application_id: int, body: CommentIn | None = None,
                         member: DepartmentMember = Depends(current_member),
                         db: Session = Depends(get_db)):
    """Передать заявку на этап решения. Решение принимает андеррайтер, не верификатор."""
    app, pl = _load(db, application_id, lock=True)
    rules.require(member, app, pl, PipelineAction.PASS_TO_UNDERWRITING)
    pipeline.pass_to_underwriting(db, member, app, pl,
                                  comment=(body.comment or "").strip() or None if body else None)
    db.commit()
    return pipeline_view(db, member, app, pl)
